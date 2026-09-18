import copy
import json
import logging
import re

from django.db import IntegrityError
from lxml import etree

from body.exceptions import BodyLlamaUnavailableError
from body.images import attach_figure_hrefs
from body.marking import mark_body
from body.models import Body
from body.utils import (
    ACK_SECTION_RE,
    apply_body_rules,
    body_checksum,
    normalize_body_text,
    sec_type_from_title,
)

logger = logging.getLogger(__name__)

XLINK_NS = "http://www.w3.org/1999/xlink"

SEC_TYPES = {
    "intro",
    "materials",
    "methods",
    "results",
    "discussion",
    "conclusions",
    "cases",
    "subjects",
    "supplementary-material",
    "transcript",
    "data-availability",
}
EXCLUSIVE_SEC_TYPES = {
    "supplementary-material",
    "transcript",
    "data-availability",
}
FIG_TYPES = {
    "graphic",
    "chart",
    "diagram",
    "drawing",
    "illustration",
    "map",
}
LIST_TYPES = {
    "order",
    "bullet",
    "alpha-lower",
    "alpha-upper",
    "roman-lower",
    "roman-upper",
    "simple",
}
XREF_TYPES = {
    "aff",
    "app",
    "author-notes",
    "bibr",
    "bio",
    "boxed-text",
    "contrib",
    "corresp",
    "disp-formula",
    "fig",
    "fn",
    "list",
    "sec",
    "supplementary-material",
    "table",
    "table-fn",
}
ID_PREFIX = {
    "sec": "sec",
    "fig": "f",
    "graphic": "g",
    "table-wrap": "t",
    "disp-formula": "e",
    "media": "md",
    "supplementary-material": "suppl",
    "transcript": "TR",
}
FIGURE_LABEL_RE = re.compile(r"^(?:fig(?:\.|ure|ura)?)\b", re.IGNORECASE)
DIGIT_RE = re.compile(r"^\d+$")
SPECIFIC_USE = {
    "data-available",
    "data-available-upon-request",
    "uninformed",
    "data-not-available",
    "data-in-article",
}


def parse_marked(choice):
    if isinstance(choice, dict):
        if "sections" in choice:
            return choice
        return {"sections": [choice]} if choice else None
    text = str(choice or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```.*$", "", text, flags=re.DOTALL)
        text = text.strip()
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj < 0 and start_arr < 0:
        return None
    if start_obj < 0:
        start = start_arr
    elif start_arr < 0:
        start = start_obj
    else:
        start = min(start_obj, start_arr)
    snippet = text[start:]
    previous = None
    while previous != snippet:
        previous = snippet
        snippet = re.sub(r",+\s*([}\]])", r"\1", snippet)
        snippet = re.sub(r",+\s*$", "", snippet)
    parsed = None
    try:
        parsed = json.loads(snippet)
    except (TypeError, json.JSONDecodeError):
        try:
            parsed, _ = json.JSONDecoder().raw_decode(snippet)
        except (TypeError, json.JSONDecodeError, ValueError):
            parsed = None
    if isinstance(parsed, list):
        return {"sections": parsed}
    if isinstance(parsed, dict):
        if "sections" in parsed:
            return parsed
        return {"sections": [parsed]} if parsed else None
    return None


def take_id(counters, kind, existing):
    value = str(existing or "").strip()
    if value:
        return value
    counters[kind] = counters.get(kind, 0) + 1
    return f"{ID_PREFIX[kind]}{counters[kind]}"


def normalize_sec_type(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = [item.strip() for item in raw.split("|") if item.strip()]
    if not parts or any(item not in SEC_TYPES for item in parts):
        return None
    if len(parts) > 1 and any(item in EXCLUSIVE_SEC_TYPES for item in parts):
        return None
    return "|".join(parts)


def append_xref(parent, xref, display=None):
    ref_type = str(xref.get("ref_type") or "").strip()
    rid = str(xref.get("rid") or "").strip()
    if ref_type not in XREF_TYPES or not rid:
        return None
    el = etree.SubElement(parent, "xref", attrib={"ref-type": ref_type, "rid": rid})
    label = str(display if display is not None else xref.get("text") or "").strip()
    if ref_type == "bibr" and DIGIT_RE.match(label):
        sup = etree.SubElement(el, "sup")
        sup.text = label
    elif label:
        el.text = label
    return el


def append_paragraph(parent, block):
    p_el = etree.SubElement(parent, "p")
    text = str(block.get("text") or "")
    xrefs = [item for item in (block.get("xrefs") or []) if isinstance(item, dict)]
    events = []
    for index, xref in enumerate(xrefs):
        needle = str(xref.get("text") or "").strip()
        if not needle:
            continue
        start = 0
        while True:
            pos = text.find(needle, start)
            if pos < 0:
                break
            events.append((pos, pos + len(needle), index, xref, needle))
            start = pos + len(needle)
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    filtered = []
    last_end = 0
    claimed = set()
    for pos, end, index, xref, needle in events:
        if pos < last_end or index in claimed:
            continue
        filtered.append((pos, end, index, xref, needle))
        claimed.add(index)
        last_end = end
    if not filtered:
        p_el.text = text
        return
    cursor = 0
    last_el = None
    for start, end, _index, xref, needle in filtered:
        chunk = text[cursor:start]
        if last_el is None:
            p_el.text = chunk
        else:
            last_el.tail = (last_el.tail or "") + chunk
        last_el = append_xref(p_el, xref, needle)
        cursor = end
    tail = text[cursor:]
    if last_el is None:
        p_el.text = (p_el.text or "") + tail
    else:
        last_el.tail = (last_el.tail or "") + tail


def append_list(parent, block):
    list_type = str(block.get("list_type") or "simple").strip()
    if list_type not in LIST_TYPES:
        list_type = "simple"
    list_el = etree.SubElement(parent, "list", attrib={"list-type": list_type})
    list_id = str(block.get("id") or "").strip()
    if list_id:
        list_el.set("id", list_id)
    title = str(block.get("title") or "").strip()
    if title:
        title_el = etree.SubElement(list_el, "title")
        title_el.text = title
    for item in block.get("items") or []:
        li = etree.SubElement(list_el, "list-item")
        if isinstance(item, dict):
            p_el = etree.SubElement(li, "p")
            p_el.text = str(item.get("text") or "")
            nested = item.get("items")
            if nested:
                append_list(
                    li,
                    {
                        "list_type": item.get("list_type") or list_type,
                        "items": nested,
                    },
                )
        else:
            p_el = etree.SubElement(li, "p")
            p_el.text = str(item)


def append_fig(parent, block, counters):
    fig = etree.SubElement(parent, "fig")
    fig.set("id", take_id(counters, "fig", block.get("id")))
    label = str(block.get("label") or "").strip()
    fig_type = str(block.get("fig_type") or "").strip()
    if fig_type in FIG_TYPES and not FIGURE_LABEL_RE.match(label):
        fig.set("fig-type", fig_type)
    if label:
        label_el = etree.SubElement(fig, "label")
        label_el.text = label
    caption = str(block.get("caption") or "").strip()
    if caption:
        caption_el = etree.SubElement(fig, "caption")
        title_el = etree.SubElement(caption_el, "title")
        title_el.text = caption
    href = str(block.get("href") or "").strip()
    alt_text = str(block.get("alt_text") or "").strip()
    if not href:
        digits = re.search(r"(\d+)", fig.get("id") or "")
        href = f"fig-{digits.group(1)}.jpg" if digits else "fig-1.jpg"
    graphic = etree.SubElement(fig, "graphic")
    graphic.set("id", take_id(counters, "graphic", None))
    graphic.set("{%s}href" % XLINK_NS, href)
    if alt_text:
        alt_el = etree.SubElement(graphic, "alt-text")
        alt_el.text = alt_text
    attrib = str(block.get("attrib") or "").strip()
    if attrib:
        attrib_el = etree.SubElement(fig, "attrib")
        attrib_el.text = attrib


def append_table_wrap(parent, block, counters):
    wrap = etree.SubElement(parent, "table-wrap")
    wrap.set("id", take_id(counters, "table-wrap", block.get("id")))
    label = str(block.get("label") or "").strip()
    caption = str(block.get("caption") or "").strip()
    if label:
        label_el = etree.SubElement(wrap, "label")
        label_el.text = label
    if caption or not label:
        caption_el = etree.SubElement(wrap, "caption")
        title_el = etree.SubElement(caption_el, "title")
        title_el.text = caption
    headers = block.get("headers") or []
    rows = block.get("rows") or []
    if headers or rows:
        table = etree.SubElement(wrap, "table")
        if headers:
            thead = etree.SubElement(table, "thead")
            tr = etree.SubElement(thead, "tr")
            for cell in headers:
                th = etree.SubElement(tr, "th")
                th.text = str(cell)
        if rows:
            tbody = etree.SubElement(table, "tbody")
            for row in rows:
                tr = etree.SubElement(tbody, "tr")
                cells = row if isinstance(row, (list, tuple)) else [row]
                for cell in cells:
                    td = etree.SubElement(tr, "td")
                    td.text = str(cell)
    attrib = str(block.get("attrib") or "").strip()
    if attrib:
        attrib_el = etree.SubElement(wrap, "attrib")
        attrib_el.text = attrib
    footnotes = block.get("footnotes") or []
    if footnotes:
        foot = etree.SubElement(wrap, "table-wrap-foot")
        for index, note in enumerate(footnotes, start=1):
            fn = etree.SubElement(foot, "fn")
            if isinstance(note, dict):
                fn.set("id", str(note.get("id") or f"TFN{index}").strip())
                note_label = str(note.get("label") or "").strip()
                if note_label:
                    lab = etree.SubElement(fn, "label")
                    lab.text = note_label
                p_el = etree.SubElement(fn, "p")
                p_el.text = str(note.get("text") or "")
            else:
                fn.set("id", f"TFN{index}")
                p_el = etree.SubElement(fn, "p")
                p_el.text = str(note)


def append_block(parent, block, counters):
    if not isinstance(block, dict):
        return
    kind = str(block.get("type") or "").strip()
    if kind == "p":
        append_paragraph(parent, block)
    elif kind == "fig":
        append_fig(parent, block, counters)
    elif kind == "fig-group":
        group = etree.SubElement(parent, "fig-group")
        group_id = str(block.get("id") or "").strip()
        if group_id:
            group.set("id", group_id)
        for fig in block.get("figs") or []:
            if isinstance(fig, dict):
                append_fig(group, fig, counters)
                language = str(fig.get("language") or "").strip()
                if language and group[-1].tag == "fig":
                    group[-1].set(
                        "{http://www.w3.org/XML/1998/namespace}lang", language
                    )
    elif kind == "table-wrap":
        append_table_wrap(parent, block, counters)
    elif kind == "list":
        append_list(parent, block)
    elif kind == "disp-formula":
        formula = etree.SubElement(parent, "disp-formula")
        formula.set("id", take_id(counters, "disp-formula", block.get("id")))
        label = str(block.get("label") or "").strip()
        if label:
            lab = etree.SubElement(formula, "label")
            lab.text = label
        text = str(block.get("text") or "").strip()
        if text:
            tex = etree.SubElement(formula, "tex-math")
            tex.text = text
    elif kind == "media":
        media = etree.SubElement(parent, "media")
        media.set("id", take_id(counters, "media", block.get("id")))
        mime_type = str(block.get("mime_type") or "").strip()
        mime_subtype = str(block.get("mime_subtype") or "").strip()
        href = str(block.get("href") or "").strip()
        if mime_type:
            media.set("mimetype", mime_type)
        if mime_subtype:
            media.set("mime-subtype", mime_subtype)
        if href:
            media.set("{%s}href" % XLINK_NS, href)
        label = str(block.get("label") or "").strip()
        if label:
            lab = etree.SubElement(media, "label")
            lab.text = label
        caption = str(block.get("caption") or "").strip()
        if caption:
            caption_el = etree.SubElement(media, "caption")
            title_el = etree.SubElement(caption_el, "title")
            title_el.text = caption
    elif kind == "supplementary-material":
        suppl = etree.SubElement(parent, "supplementary-material")
        suppl.set("id", take_id(counters, "supplementary-material", block.get("id")))
        label = str(block.get("label") or "").strip()
        if label:
            lab = etree.SubElement(suppl, "label")
            lab.text = label
        caption = str(block.get("caption") or "").strip()
        if caption:
            caption_el = etree.SubElement(suppl, "caption")
            title_el = etree.SubElement(caption_el, "title")
            title_el.text = caption
        href = str(block.get("href") or "").strip()
        mime_type = str(block.get("mime_type") or "").strip()
        mime_subtype = str(block.get("mime_subtype") or "").strip()
        if (
            mime_type
            or mime_subtype
            or (
                href
                and href.lower().endswith((".mp4", ".mp3", ".pdf", ".zip", ".xlsx"))
            )
        ):
            media = etree.SubElement(suppl, "media")
            if mime_type:
                media.set("mimetype", mime_type)
            if mime_subtype:
                media.set("mime-subtype", mime_subtype)
            if href:
                media.set("{%s}href" % XLINK_NS, href)
        elif href:
            graphic = etree.SubElement(suppl, "graphic")
            graphic.set("id", take_id(counters, "graphic", None))
            graphic.set("{%s}href" % XLINK_NS, href)
    elif kind == "disp-quote":
        quote = etree.SubElement(parent, "disp-quote")
        text = str(block.get("text") or "").strip()
        if text:
            p_el = etree.SubElement(quote, "p")
            p_el.text = text
        attrib = str(block.get("attrib") or "").strip()
        if attrib:
            attrib_el = etree.SubElement(quote, "attrib")
            attrib_el.text = attrib


def append_sec(parent, section, counters, first_level):
    if not isinstance(section, dict):
        return
    title = str(section.get("title") or "").strip()
    if not title:
        return
    sec_el = etree.SubElement(parent, "sec")
    sec_type = normalize_sec_type(section.get("sec_type"))
    if first_level and not sec_type:
        sec_type = normalize_sec_type(sec_type_from_title(title))
    if first_level and sec_type:
        sec_el.set("sec-type", sec_type)
        kind = "transcript" if sec_type == "transcript" else "sec"
        sec_el.set("id", take_id(counters, kind, section.get("id")))
        specific = str(section.get("specific_use") or "").strip()
        if sec_type == "data-availability":
            if specific not in SPECIFIC_USE:
                pieces = []
                stack = [section]
                while stack:
                    current = stack.pop()
                    if not isinstance(current, dict):
                        continue
                    pieces.append(str(current.get("title") or ""))
                    for block in current.get("content") or []:
                        if isinstance(block, dict):
                            pieces.append(str(block.get("text") or ""))
                    stack.extend(current.get("sections") or [])
                folded = " ".join(pieces).casefold()
                if (
                    "upon request" in folded
                    or "a pedido" in folded
                    or "corresponding author" in folded
                    or "autor correspondente" in folded
                ):
                    specific = "data-available-upon-request"
                elif (
                    "not available" in folded
                    or "não disponível" in folded
                    or "nao disponivel" in folded
                ):
                    specific = "data-not-available"
                elif (
                    "in the article" in folded
                    or "in this article" in folded
                    or "no próprio artigo" in folded
                    or "neste artigo" in folded
                ):
                    specific = "data-in-article"
                elif "uninformed" in folded or "não informado" in folded:
                    specific = "uninformed"
                elif re.search(
                    r"https?://|doi\.org|repository|reposit[oó]rio|"
                    r"available at|dispon[ií]ve",
                    folded,
                ):
                    specific = "data-available"
                else:
                    specific = "uninformed"
            sec_el.set("specific-use", specific)
    else:
        sec_id = str(section.get("id") or "").strip()
        if sec_id:
            sec_el.set("id", sec_id)
        else:
            sec_el.set("id", take_id(counters, "sec", None))
    title_el = etree.SubElement(sec_el, "title")
    title_el.text = title
    for block in section.get("content") or []:
        if (
            first_level
            and sec_type == "supplementary-material"
            and isinstance(block, dict)
        ):
            block = {key: value for key, value in block.items() if key != "parts"}
        append_block(sec_el, block, counters)
    for child in section.get("sections") or []:
        append_sec(sec_el, child, counters, first_level=False)


def is_ack_section(section):
    if not isinstance(section, dict):
        return False
    sec_type = str(section.get("sec_type") or "").strip()
    if sec_type == "acknowledgments":
        return True
    title = str(section.get("title") or "").strip()
    return bool(ACK_SECTION_RE.match(title))


def append_ack(parent, section, counters):
    ack = etree.SubElement(parent, "ack")
    title = str(section.get("title") or "").strip()
    if title:
        title_el = etree.SubElement(ack, "title")
        title_el.text = title
    for block in section.get("content") or []:
        append_block(ack, block, counters)


def body_section_kind(section):
    if is_ack_section(section):
        return "ack"
    title = str(section.get("title") or "").strip()
    sec_type = str(section.get("sec_type") or sec_type_from_title(title) or "").strip()
    if sec_type == "supplementary-material":
        return "supplementary-material"
    if sec_type == "data-availability":
        return "data-availability"
    return "regular"


def get_body_xml(data):
    marked = data if isinstance(data, dict) else {}
    body = etree.Element("body", nsmap={"xlink": XLINK_NS})
    counters = {}
    regular = []
    acks = []
    data_availability = []
    supplementary = []
    for section in marked.get("sections") or []:
        kind = body_section_kind(section)
        if kind == "ack":
            acks.append(section)
        elif kind == "data-availability":
            data_availability.append(section)
        elif kind == "supplementary-material":
            supplementary.append(section)
        else:
            regular.append(section)
    for section in regular:
        append_sec(body, section, counters, first_level=True)
    for section in acks:
        append_ack(body, section, counters)
    for section in data_availability:
        append_sec(body, section, counters, first_level=True)
    for section in supplementary:
        append_sec(body, section, counters, first_level=True)
    return etree.tostring(body, pretty_print=True, encoding="unicode")


def resolve_body_result(
    body_text,
    user=None,
    output_type="json",
    language=None,
    tables=None,
    figures=None,
    image_hrefs=None,
):
    normalized = normalize_body_text(body_text)
    checksum = body_checksum(normalized)

    try:
        record = Body.objects.get(checksum=checksum)
    except Body.DoesNotExist:
        raw = mark_body(body_text)
        marked = parse_marked(raw)
        if marked is None:
            preview = str(raw or "")
            logger.warning(
                "Body Llama invalid JSON (%d chars): %r",
                len(preview),
                preview[:500],
            )
            raise BodyLlamaUnavailableError("Body Llama returned invalid JSON")
        if figures:
            marked.setdefault("figures", [])
            marked["figures"] = list(marked.get("figures") or []) + [
                item for item in figures if isinstance(item, dict)
            ]
        marked = apply_body_rules(marked, body_text, tables=tables)
        xml = get_body_xml(marked)
        try:
            record, created = Body.objects.get_or_create(
                checksum=checksum,
                defaults={
                    "source_text": body_text,
                    "marked": marked,
                    "marked_xml": xml,
                    "creator": user,
                },
            )
        except IntegrityError:
            record = Body.objects.get(checksum=checksum)
            created = False
        if not created and not record.marked:
            record.marked = marked
            record.marked_xml = xml
            record.save(update_fields=["marked", "marked_xml", "updated"])

    marked = record.marked
    xml = record.marked_xml
    if image_hrefs:
        marked = copy.deepcopy(record.marked)
        attach_figure_hrefs(marked, image_hrefs)
        xml = get_body_xml(marked)
    if output_type == "xml":
        data = xml
    else:
        data = marked
    return {"data": data}
