import hashlib
import os
import re
import tempfile
import zipfile

from lxml import etree

from body.exceptions import BodyDocxError

BODY_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"introduction|introdução|introducao|introducción|introduccion|"
    r"methods?|metodologia|metodología|methodology|"
    r"materials?(?:\s+and\s+methods?)?|"
    r"material(?:es)?(?:\s+y\s+métodos)?|"
    r"results?\s+(?:and|&)\s+discussion|"
    r"resultados?\s+e\s+discuss[aã]o|"
    r"results?|resultados|"
    r"discussion|discussão|discusion|"
    r"conclus(?:ions?|ão|ões|iones)?|"
    r"considerações?\s+finais|"
    r"consideraciones?\s+finales|"
    r"data\s+availability|"
    r"disponibilidade\s+de\s+dados|"
    r"supplementary\s+materials?|"
    r"material\s+suplementar|"
    r"acknowledg(?:e?ments?)?|agradecimentos?"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

BODY_REFERENCE_STOP_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"references|refer[eê]ncias|referencias?|"
    r"bibliography|bibliografia"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

BODY_EDITORIAL_SKIP_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"authors?'?\s+contributions?|"
    r"contribui[cç][aã]o\s+dos\s+autores|"
    r"conflicts?\s+of\s+interest|"
    r"conflitos?\s+de\s+interesses?|"
    r"ethics|associate\s+editor"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

NESTED_HEADING_RE = re.compile(
    r"^\d+(?:\.\d+)+\.?\s+[A-ZÀ-Ý].{0,120}$|^\d+\.\s+[A-ZÀ-Ý].{0,120}$"
)
CAPTION_RE = re.compile(
    r"^(?P<kind>figure|fig\.|figura|table|tabela|quadro)\s+"
    r"(?P<num>\d+)\s*(?:[.:\u2013\u2014\-–—])?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
SOURCE_RE = re.compile(r"^(?:fonte|source)\s*:\s*(.+)$", re.IGNORECASE)
FIG_MENTION_RE = re.compile(
    r"\b((?:figures?|figs?\.?|figuras?)\s+(?![sS]\d)(\d+))",
    re.IGNORECASE,
)
TABLE_MENTION_RE = re.compile(
    r"\b((?:tables?|tabelas?|quadros?)\s+(\d+))",
    re.IGNORECASE,
)
PAREN_RE = re.compile(r"\(([^()]{3,220})\)")
NARRATIVE_CITE_RE = re.compile(
    r"\b((?:(?:van|von|ter|de|da|do|dos|das|del)\s+)?"
    r"[A-ZÀ-Ý][\w'`-]*"
    r"(?:\s+(?:and|&|e)\s+[A-ZÀ-Ý][\w'`-]*)?"
    r"(?:\s+et\s+al\.)?)\s*\((\d{4}[a-z]?)\)"
)
YEAR_RE = re.compile(r"\b(?:1[7-9]|20)\d{2}[a-z]?\b")
CITE_LEAD_RE = re.compile(r"^(?:e\.g\.|eg\.|i\.e\.|cf\.)[,:]?\s*", re.IGNORECASE)
NUM_CITE_RE = re.compile(r"(?<=\.)(\d{1,3}(?:\s*[-–]\s*\d{1,3})+)(?!\d)")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_NSMAP = {"w": W_NS}


def normalize_body_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def body_checksum(normalized):
    return hashlib.sha256(f"body-v8\n{normalized}".encode()).hexdigest()


def extract_body_section(text):
    if not text:
        return ""
    lines = str(text).split("\n")
    start = None
    for index, line in enumerate(lines):
        if BODY_HEADING_RE.match(line.strip()):
            start = index
            break
    found_heading = start is not None
    if start is None:
        start = 0
    end = len(lines)
    scan_from = start + 1 if found_heading else 0
    for index in range(scan_from, len(lines)):
        if BODY_REFERENCE_STOP_RE.match(lines[index].strip()):
            end = index
            break
    selected = lines[start:end]
    kept = []
    skip = False
    for line in selected:
        stripped = line.strip()
        if BODY_EDITORIAL_SKIP_RE.match(stripped):
            skip = True
            continue
        if skip:
            if stripped and BODY_HEADING_RE.match(stripped):
                skip = False
            else:
                continue
        if stripped:
            kept.append(stripped)
    return "\n".join(kept)


def split_body_sections(text):
    lines = str(text or "").split("\n")
    headings = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and BODY_HEADING_RE.match(stripped):
            headings.append(index)
    if not headings:
        body = "\n".join(line.strip() for line in lines if line.strip())
        return [{"title": "", "text": body}] if body else []
    parts = []
    for index, start in enumerate(headings):
        end = headings[index + 1] if index + 1 < len(headings) else len(lines)
        title = lines[start].strip()
        chunk_lines = [line.strip() for line in lines[start:end] if line.strip()]
        parts.append({"title": title, "text": "\n".join(chunk_lines)})
    return parts


def split_text_windows(text, max_chars):
    raw = str(text or "")
    limit = max(1000, int(max_chars or 8000))
    if len(raw) <= limit:
        return [raw] if raw.strip() else []
    parts = []
    buf = []
    size = 0
    for line in raw.split("\n"):
        extra = len(line) + 1
        if buf and size + extra > limit:
            parts.append("\n".join(buf))
            buf = [line]
            size = extra
        else:
            buf.append(line)
            size += extra
    if buf:
        parts.append("\n".join(buf))
    return parts


def sec_type_from_title(title):
    raw = re.sub(r"^\d+[.\)]\s*", "", str(title or "").strip())
    raw = re.sub(r"\s+", " ", raw).lower()
    if not raw:
        return None
    if re.fullmatch(r"introdu[cç][aã]o|introducci[oó]n|introduction|intro", raw):
        return "intro"
    if re.search(r"material.+\b(?:m[eé]todos?|methods?)\b", raw):
        return "materials|methods"
    if re.fullmatch(r"methods?|metodologia|metodolog[ií]a|methodology", raw):
        return "methods"
    if re.fullmatch(r"materials?|materiais|materiales", raw):
        return "materials"
    if re.search(r"result.+discuss", raw):
        return "results|discussion"
    if re.fullmatch(r"results?|resultados", raw):
        return "results"
    if re.fullmatch(r"discussion|discuss[aã]o|discusi[oó]n", raw):
        return "discussion"
    if (
        raw.startswith("conclus")
        or "considerações finais" in raw
        or "consideraciones finales" in raw
    ):
        return "conclusions"
    if re.fullmatch(r"acknowledg(e)?ments?|agradecimentos?", raw):
        return "acknowledgments"
    if "supplementary" in raw or "material suplementar" in raw:
        return "supplementary-material"
    if "data availability" in raw or "disponibilidade de dados" in raw:
        return "data-availability"
    if "transcript" in raw:
        return "transcript"
    if re.fullmatch(r"cases?|casos", raw):
        return "cases"
    if re.fullmatch(r"subjects?|sujeitos|sujetos", raw):
        return "subjects"
    return None


def parse_lines_to_blocks(lines):
    content = []
    for line in lines:
        source = SOURCE_RE.match(line)
        if (
            source
            and content
            and isinstance(content[-1], dict)
            and content[-1].get("type") in {"fig", "table-wrap"}
        ):
            content[-1]["attrib"] = source.group(1).strip()
            continue
        caption = CAPTION_RE.match(line)
        if caption:
            kind = caption.group("kind").lower()
            num = caption.group("num")
            rest = caption.group("rest").strip()
            if kind.startswith("tab") or kind == "quadro":
                label = f"Table {num}" if kind.startswith("tab") else f"Quadro {num}"
                if kind.startswith("tabela"):
                    label = f"Tabela {num}"
                content.append(
                    {
                        "type": "table-wrap",
                        "id": f"t{num}",
                        "label": label,
                        "caption": rest,
                    }
                )
            else:
                label = f"Figure {num}"
                if kind.startswith("figura"):
                    label = f"Figura {num}"
                content.append(
                    {
                        "type": "fig",
                        "id": f"f{num}",
                        "label": label,
                        "caption": rest,
                    }
                )
            continue
        content.append({"type": "p", "text": line})
    return content


def section_from_plain_text(title, text):
    lines = [line.strip() for line in str(text or "").split("\n") if line.strip()]
    heading = str(title or "").strip()
    if heading and lines and lines[0] == heading:
        lines = lines[1:]
    nested_at = [
        index for index, line in enumerate(lines) if NESTED_HEADING_RE.match(line)
    ]
    if not nested_at:
        return {
            "title": heading or "Body",
            "sec_type": sec_type_from_title(heading),
            "content": parse_lines_to_blocks(lines),
            "sections": [],
        }
    preamble = lines[: nested_at[0]]
    nested = []
    for index, start in enumerate(nested_at):
        end = nested_at[index + 1] if index + 1 < len(nested_at) else len(lines)
        nested.append(
            {
                "title": lines[start],
                "content": parse_lines_to_blocks(lines[start + 1 : end]),
                "sections": [],
            }
        )
    return {
        "title": heading or "Body",
        "sec_type": sec_type_from_title(heading),
        "content": parse_lines_to_blocks(preamble),
        "sections": nested,
    }


def find_named_section(sections, title):
    want = re.sub(r"\s+", " ", str(title or "").strip()).casefold()
    if not want:
        return None
    for item in sections or []:
        if not isinstance(item, dict):
            continue
        got = re.sub(r"\s+", " ", str(item.get("title") or "").strip()).casefold()
        if got == want:
            return item
    return None


def apply_outline(skeleton, outline):
    data = skeleton if isinstance(skeleton, dict) else {"sections": []}
    if not isinstance(outline, dict):
        return data
    allowed = {
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
        "acknowledgments",
    }
    exclusive = {
        "supplementary-material",
        "transcript",
        "data-availability",
        "acknowledgments",
    }
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        match = find_named_section(outline.get("sections") or [], section.get("title"))
        if not match:
            continue
        raw_type = str(match.get("sec_type") or "").strip()
        parts = [item.strip() for item in raw_type.split("|") if item.strip()]
        if (
            parts
            and all(item in allowed for item in parts)
            and not (len(parts) > 1 and any(item in exclusive for item in parts))
            and not str(section.get("sec_type") or "").strip()
        ):
            section["sec_type"] = "|".join(parts)
        specific = str(match.get("specific_use") or "").strip()
        if specific:
            section["specific_use"] = specific
        nested_out = match.get("sections") or []
        for child in section.get("sections") or []:
            if not isinstance(child, dict):
                continue
            nested_match = find_named_section(nested_out, child.get("title"))
            if nested_match and nested_match.get("title"):
                child["title"] = str(nested_match.get("title") or child["title"])
    figures = outline.get("figures")
    if figures:
        data["figures"] = figures
    return data


def iter_content_lists(section):
    if not isinstance(section, dict):
        return
    yield section.setdefault("content", [])
    for child in section.get("sections") or []:
        yield from iter_content_lists(child)


def cite_rid(cite_ids, text):
    key = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not key:
        return None
    if key not in cite_ids:
        cite_ids[key] = f"B{len(cite_ids) + 1}"
    return cite_ids[key]


def annotate_paragraph(text, cite_ids):
    original = str(text or "")
    events = []
    for match in FIG_MENTION_RE.finditer(original):
        events.append(
            (
                match.start(),
                match.end(),
                {
                    "ref_type": "fig",
                    "rid": f"f{match.group(2)}",
                    "text": match.group(1),
                },
            )
        )
    for match in TABLE_MENTION_RE.finditer(original):
        events.append(
            (
                match.start(),
                match.end(),
                {
                    "ref_type": "table",
                    "rid": f"t{match.group(2)}",
                    "text": match.group(1),
                },
            )
        )
    for match in NARRATIVE_CITE_RE.finditer(original):
        label = f"{match.group(1)} ({match.group(2)})"
        events.append(
            (
                match.start(),
                match.end(),
                {
                    "ref_type": "bibr",
                    "rid": cite_rid(cite_ids, label),
                    "text": label,
                },
            )
        )
    for match in PAREN_RE.finditer(original):
        inner = match.group(1)
        if not YEAR_RE.search(inner):
            continue
        if re.search(r"https?://|www\.|°|º|\d+['′]\s*\d+", inner, re.IGNORECASE):
            continue
        cursor = match.start() + 1
        for piece in re.split(r"\s*;\s*", inner):
            piece = piece.strip()
            if not piece or not YEAR_RE.search(piece):
                cursor += len(piece) + 1
                continue
            lead = CITE_LEAD_RE.match(piece)
            core = piece[lead.end() :] if lead else piece
            if not core or not YEAR_RE.search(core):
                cursor += len(piece) + 1
                continue
            start = original.find(core, cursor)
            if start < 0:
                start = original.find(piece, cursor)
                if start < 0:
                    start = cursor
                elif lead:
                    start += lead.end()
            year_matches = list(YEAR_RE.finditer(core))
            if len(year_matches) >= 2:
                prefix = core[: year_matches[0].start()].strip()
                first_year = year_matches[0].group(0)
                first_label = f"{prefix} {first_year}".strip() if prefix else first_year
                events.append(
                    (
                        start,
                        start + year_matches[0].end(),
                        {
                            "ref_type": "bibr",
                            "rid": cite_rid(cite_ids, first_label),
                            "text": first_label,
                        },
                    )
                )
                for year_match in year_matches[1:]:
                    label = year_match.group(0)
                    events.append(
                        (
                            start + year_match.start(),
                            start + year_match.end(),
                            {
                                "ref_type": "bibr",
                                "rid": cite_rid(cite_ids, label),
                                "text": label,
                            },
                        )
                    )
            else:
                events.append(
                    (
                        start,
                        start + len(core),
                        {
                            "ref_type": "bibr",
                            "rid": cite_rid(cite_ids, core),
                            "text": core,
                        },
                    )
                )
            cursor = start + len(core)
    for match in NUM_CITE_RE.finditer(original):
        events.append(
            (
                match.start(),
                match.end(),
                {
                    "ref_type": "bibr",
                    "rid": cite_rid(cite_ids, match.group(1)),
                    "text": match.group(1),
                },
            )
        )
    events.sort(key=lambda item: (item[0], item[1]))
    filtered = []
    last_end = 0
    xrefs = []
    for start, end, xref in events:
        if start < last_end or end <= start:
            continue
        filtered.append((start, end, xref))
        xrefs.append(xref)
        last_end = end
    block = {"type": "p", "text": original}
    if xrefs:
        block["xrefs"] = xrefs
    return block


def captions_from_text(source_text):
    figs = {}
    tables = {}
    pending = None
    for line in str(source_text or "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        source = SOURCE_RE.match(stripped)
        if source and pending:
            kind, num = pending
            target = figs if kind == "fig" else tables
            if num in target:
                target[num]["attrib"] = source.group(1).strip()
            pending = None
            continue
        caption = CAPTION_RE.match(stripped)
        if not caption:
            pending = None
            continue
        kind_raw = caption.group("kind").lower()
        num = caption.group("num")
        rest = caption.group("rest").strip()
        if kind_raw.startswith("tab") or kind_raw == "quadro":
            label = f"Table {num}"
            if kind_raw.startswith("tabela"):
                label = f"Tabela {num}"
            elif kind_raw == "quadro":
                label = f"Quadro {num}"
            tables[num] = {
                "type": "table-wrap",
                "id": f"t{num}",
                "label": label,
                "caption": rest,
            }
            pending = ("table", num)
        else:
            label = f"Figure {num}"
            if kind_raw.startswith("figura"):
                label = f"Figura {num}"
            figs[num] = {
                "type": "fig",
                "id": f"f{num}",
                "label": label,
                "caption": rest,
            }
            pending = ("fig", num)
    return figs, tables


def float_number(block):
    label = str((block or {}).get("label") or (block or {}).get("id") or "")
    match = re.search(r"(\d+)", label)
    return match.group(1) if match else ""


def fill_float_caption(sections, kind, number, incoming):
    caption = str((incoming or {}).get("caption") or "").strip()
    attrib = str((incoming or {}).get("attrib") or "").strip()
    label = str((incoming or {}).get("label") or "").strip()
    href = str((incoming or {}).get("href") or "").strip()
    if not caption and not attrib and not label and not href:
        return
    for section in sections or []:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != kind:
                    continue
                if float_number(block) != number:
                    continue
                if caption and not str(block.get("caption") or "").strip():
                    block["caption"] = caption
                if attrib and not str(block.get("attrib") or "").strip():
                    block["attrib"] = attrib
                if label and not str(block.get("label") or "").strip():
                    block["label"] = label
                if href and not str(block.get("href") or "").strip():
                    block["href"] = href


def existing_float_numbers(sections):
    figs = set()
    tables = set()
    for section in sections or []:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict):
                    continue
                num = float_number(block)
                if not num:
                    continue
                if block.get("type") == "fig":
                    figs.add(num)
                elif block.get("type") == "table-wrap":
                    tables.add(num)
    return figs, tables


def insert_float_after_mention(sections, float_block, mention_re, number):
    needle = None
    for section in sections or []:
        for content in iter_content_lists(section):
            for index, block in enumerate(content):
                if not isinstance(block, dict) or block.get("type") != "p":
                    continue
                text = str(block.get("text") or "")
                for match in mention_re.finditer(text):
                    if match.group(2) == number:
                        needle = (content, index)
                        break
                if needle:
                    break
            if needle:
                break
        if needle:
            break
    if needle is None:
        if sections:
            lists = list(iter_content_lists(sections[-1]))
            if lists:
                lists[-1].append(float_block)
        return
    content, index = needle
    content.insert(index + 1, float_block)


ACK_SECTION_RE = re.compile(
    r"^(?:acknowledg(?:e?ments?)?|agradecimentos?)\s*$",
    re.IGNORECASE,
)


def infer_data_availability_specific_use(section):
    pieces = [str(section.get("title") or "")]
    for block in section.get("content") or []:
        if isinstance(block, dict):
            pieces.append(str(block.get("text") or ""))
    for child in section.get("sections") or []:
        if isinstance(child, dict):
            pieces.append(str(child.get("title") or ""))
            for block in child.get("content") or []:
                if isinstance(block, dict):
                    pieces.append(str(block.get("text") or ""))
    folded = " ".join(pieces).casefold()
    if (
        "upon request" in folded
        or "a pedido" in folded
        or "corresponding author" in folded
        or "autor correspondente" in folded
    ):
        return "data-available-upon-request"
    if (
        "not available" in folded
        or "não disponível" in folded
        or "nao disponivel" in folded
    ):
        return "data-not-available"
    if (
        "in the article" in folded
        or "in this article" in folded
        or "no próprio artigo" in folded
        or "neste artigo" in folded
    ):
        return "data-in-article"
    if "uninformed" in folded or "não informado" in folded or "nao informado" in folded:
        return "uninformed"
    if re.search(
        r"https?://|doi\.org|repository|reposit[oó]rio|available at|dispon[ií]ve",
        folded,
    ):
        return "data-available"
    return "uninformed"


def enrich_tail_sections(sections):
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        inferred = sec_type_from_title(title)
        if inferred and not str(section.get("sec_type") or "").strip():
            section["sec_type"] = inferred
        sec_type = str(section.get("sec_type") or inferred or "").strip()
        if sec_type == "data-availability" and not section.get("specific_use"):
            section["specific_use"] = infer_data_availability_specific_use(section)
        if sec_type == "supplementary-material":
            for block in section.get("content") or []:
                if isinstance(block, dict):
                    block.pop("parts", None)
        enrich_tail_sections(section.get("sections") or [])


def apply_body_rules(marked, source_text, tables=None):
    data = marked if isinstance(marked, dict) else {"sections": []}
    sections = data.setdefault("sections", [])
    cite_ids = {}
    for section in sections:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "p":
                    continue
                annotated = annotate_paragraph(block.get("text") or "", cite_ids)
                if block.get("xrefs"):
                    have = {
                        (item.get("ref_type"), item.get("text"))
                        for item in block["xrefs"]
                        if isinstance(item, dict)
                    }
                    extra = [
                        item
                        for item in annotated.get("xrefs") or []
                        if (item.get("ref_type"), item.get("text")) not in have
                    ]
                    if extra:
                        block["xrefs"] = list(block["xrefs"]) + extra
                elif annotated.get("xrefs"):
                    block["xrefs"] = annotated["xrefs"]
    have_figs, have_tables = existing_float_numbers(sections)
    figs, table_caps = captions_from_text(source_text)
    for item in data.pop("figures", None) or []:
        if not isinstance(item, dict):
            continue
        num = float_number(item)
        if not num:
            continue
        caption = str(item.get("caption") or "").strip()
        attrib = str(item.get("attrib") or "").strip()
        label = str(item.get("label") or "").strip() or f"Figure {num}"
        href = str(item.get("href") or "").strip()
        if num not in figs:
            figs[num] = {
                "type": "fig",
                "id": str(item.get("id") or f"f{num}").strip() or f"f{num}",
                "label": label,
                "caption": caption,
            }
            if attrib:
                figs[num]["attrib"] = attrib
            if href:
                figs[num]["href"] = href
        else:
            if caption and not str(figs[num].get("caption") or "").strip():
                figs[num]["caption"] = caption
            if attrib and not str(figs[num].get("attrib") or "").strip():
                figs[num]["attrib"] = attrib
            if href and not str(figs[num].get("href") or "").strip():
                figs[num]["href"] = href
    for match in FIG_MENTION_RE.finditer(str(source_text or "")):
        num = match.group(2)
        if num not in figs:
            figs[num] = {
                "type": "fig",
                "id": f"f{num}",
                "label": f"Figure {num}",
                "caption": "",
            }
    for num, block in figs.items():
        if num not in have_figs:
            insert_float_after_mention(sections, block, FIG_MENTION_RE, num)
            have_figs.add(num)
        else:
            fill_float_caption(sections, "fig", num, block)
    for num, block in table_caps.items():
        if num not in have_tables:
            insert_float_after_mention(sections, block, TABLE_MENTION_RE, num)
            have_tables.add(num)
    remaining = list(tables or [])
    for section in sections:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "table-wrap":
                    continue
                if block.get("rows") or block.get("headers"):
                    continue
                label = str(block.get("label") or block.get("id") or "")
                num = ""
                found = re.search(r"(\d+)", label)
                if found:
                    num = found.group(1)
                match = None
                for item in remaining:
                    if str(item.get("number") or "") == num:
                        match = item
                        break
                if match is None and remaining:
                    match = remaining[0]
                if match is None:
                    continue
                block["headers"] = match.get("headers") or []
                block["rows"] = match.get("rows") or []
                if not str(block.get("caption") or "").strip():
                    caption = str(match.get("caption") or "").strip()
                    if caption:
                        block["caption"] = caption
                remaining.remove(match)
    if remaining and sections:
        lists = list(iter_content_lists(sections[-1]))
        target = lists[-1] if lists else sections[-1].setdefault("content", [])
        for item in remaining:
            num = str(item.get("number") or len(target) + 1)
            target.append(
                {
                    "type": "table-wrap",
                    "id": f"t{num}",
                    "label": item.get("label") or f"Table {num}",
                    "caption": item.get("caption") or "",
                    "headers": item.get("headers") or [],
                    "rows": item.get("rows") or [],
                }
            )
    enrich_tail_sections(sections)
    return data


def paragraph_text(paragraph):
    return "".join(
        node.text or "" for node in paragraph.xpath(".//w:t", namespaces=DOCX_NSMAP)
    ).strip()


def iter_docx_blocks(root):
    body = root.find(f".//{{{W_NS}}}body")
    if body is None:
        return
    stack = [iter(list(body))]
    while stack:
        try:
            child = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        tag = child.tag.split("}")[-1] if isinstance(child.tag, str) else ""
        if tag == "p":
            yield "p", child
        elif tag == "tbl":
            yield "tbl", child
        elif tag == "sdt":
            content = child.find(f"{{{W_NS}}}sdtContent")
            if content is not None:
                stack.append(iter(list(content)))
        elif tag in {"sdtContent", "ins", "del"}:
            stack.append(iter(list(child)))


def matrix_from_tbl(tbl):
    rows = []
    for tr in tbl.xpath("./w:tr", namespaces=DOCX_NSMAP):
        row = []
        for tc in tr.xpath("./w:tc", namespaces=DOCX_NSMAP):
            texts = []
            for para in tc.xpath("./w:p", namespaces=DOCX_NSMAP):
                value = paragraph_text(para)
                if value:
                    texts.append(value)
            row.append(" ".join(texts))
        if any(cell for cell in row):
            rows.append(row)
    return rows


def body_from_docx_upload(uploaded):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path) as archive:
            xml_bytes = archive.read("word/document.xml")
        root = etree.fromstring(xml_bytes)
        paragraphs = []
        tables = []
        last_paragraph = ""
        for kind, node in iter_docx_blocks(root):
            if kind == "p":
                text = paragraph_text(node)
                if text:
                    paragraphs.append(text)
                    last_paragraph = text
                continue
            rows = matrix_from_tbl(node)
            if not rows:
                continue
            caption_line = last_paragraph
            caption = CAPTION_RE.match(caption_line)
            number = caption.group("num") if caption else str(len(tables) + 1)
            rest = caption.group("rest").strip() if caption else ""
            kind_name = caption.group("kind").lower() if caption else "table"
            label = f"Table {number}"
            if kind_name.startswith("tabela"):
                label = f"Tabela {number}"
            elif kind_name == "quadro":
                label = f"Quadro {number}"
            headers = rows[0]
            body_rows = rows[1:] if len(rows) > 1 else []
            tables.append(
                {
                    "number": number,
                    "label": label,
                    "caption": rest,
                    "headers": headers,
                    "rows": body_rows,
                }
            )
        document_text = "\n".join(paragraphs)
    except BodyDocxError:
        raise
    except Exception as exc:
        raise BodyDocxError("Could not read DOCX file") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    body_text = extract_body_section(document_text)
    if not body_text.strip():
        raise BodyDocxError("No body section found in DOCX")
    lowered = body_text.lower()
    in_body = []
    for table in tables:
        caption = str(table.get("caption") or "")
        label = str(table.get("label") or "")
        if label and label.lower() in lowered:
            in_body.append(table)
        elif caption and caption in body_text:
            in_body.append(table)
    if not in_body:
        in_body = tables
    figs, _table_caps = captions_from_text(document_text)
    return body_text, in_body, list(figs.values())
