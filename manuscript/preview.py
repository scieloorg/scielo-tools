import html
import logging
import re

from django.utils.dates import MONTHS
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from lxml import etree
from lxml import html as lhtml
from packtools import HTMLGenerator

logger = logging.getLogger(__name__)

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _join_html(parts):
    return format_html_join("", "{}", ((part,) for part in parts))


def _static_html(markup):
    return SafeString(markup)


class ManuscriptPreviewError(Exception):
    pass


def _text(node):
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _node_lang(node):
    return (node.get("{http://www.w3.org/XML/1998/namespace}lang") or "").strip()


def _kwd_group_html(kwd_group):
    keywords = [_text(k) for k in kwd_group.findall("kwd") if _text(k)]
    if not keywords:
        return ""
    label = _text(kwd_group.find("title")) or "Keywords"
    return format_html(
        "<p class='paragraph'><strong>{}</strong> {}</p>",
        label,
        ", ".join(keywords),
    )


def _timeline_section(title, items):
    if not items:
        return ""
    return format_html(
        "<section class='articleSection'>"
        "<h2 class='articleSectionTitle'>{}</h2>"
        "<ul class='articleTimeline'>{}</ul>"
        "</section>",
        title,
        format_html_join("", "<li><strong>{}</strong><br>{}</li>", items),
    )


def _jats_table_section_html(section, wrapper, header):
    rows = []
    for tr in section.findall("tr"):
        if section.tag == "table" and tr.getparent() is not section:
            continue
        if header:
            cells = tr.findall("th") or tr.findall("td")
            cell_html = format_html_join(
                "", "<th>{}</th>", ((_text(c),) for c in cells)
            )
        else:
            cells = tr.findall("td") or tr.findall("th")
            cell_html = format_html_join(
                "", "<td>{}</td>", ((_text(c),) for c in cells)
            )
        if cell_html:
            rows.append(format_html("<tr>{}</tr>", cell_html))
    if not rows:
        return ""
    inner = _join_html(rows)
    if wrapper == "thead":
        return format_html("<thead>{}</thead>", inner)
    return format_html("<tbody>{}</tbody>", inner)


def figure_urls_for_manuscript(manuscript):
    urls = {}
    for item in manuscript.figure_files.all():
        if item.href and item.file:
            urls[item.href] = item.file.url
    return urls


def _fig_graphic_href(fig):
    graphic = fig.find("graphic")
    if graphic is None:
        return ""
    return (graphic.get(XLINK_HREF) or "").strip()


def _fig_alt_text(fig):
    graphic = fig.find("graphic")
    if graphic is not None:
        alt = graphic.find("alt-text")
        if alt is not None:
            text = _text(alt)
            if text:
                return text
    caption = _text(fig.find("caption"))
    if caption:
        return caption
    return _text(fig.find("label"))


def _render_fig_preview(fig, figure_urls=None):
    label = _text(fig.find("label"))
    caption = _text(fig.find("caption"))
    parts = [_static_html("<figure class='fig'>")]
    href = _fig_graphic_href(fig)
    mapping = figure_urls or {}
    if href and href in mapping:
        parts.append(
            format_html(
                '<img class="graphic" src="{}" alt="{}">',
                mapping[href],
                _fig_alt_text(fig),
            )
        )
    parts.append(
        format_html(
            "<figcaption><strong>{}</strong> {}</figcaption></figure>",
            label,
            caption,
        )
    )
    return _join_html(parts)


def render_front_preview(marked_xml):
    if not (marked_xml or "").strip():
        return format_html(
            "<p class='alert alert-info'>{}</p>", gettext("No front markup yet.")
        )
    try:
        root = etree.fromstring(marked_xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return format_html(
            "<p class='alert alert-danger'>{}</p>", gettext("Invalid front XML.")
        )
    parts = []
    title = _text(root.find(".//article-title"))
    if title:
        parts.append(format_html("<h1 class='article-title'>{}</h1>", title))
    authors = []
    for contrib in root.findall(".//contrib"):
        name = _text(contrib.find(".//name"))
        if name:
            authors.append(format_html("<span>{}</span>", name))
    if authors:
        parts.append(
            format_html(
                '<div class="contribGroup">{}</div>',
                format_html_join(" ", "{}", ((author,) for author in authors)),
            )
        )
    abstracts = []
    for tag in ("abstract", "trans-abstract"):
        abstracts.extend(root.findall(f".//{tag}"))
    kwd_groups = list(root.findall(".//kwd-group"))
    assigned = [None] * len(abstracts)
    used = set()
    for i, abstract in enumerate(abstracts):
        lang = _node_lang(abstract)
        if not lang:
            continue
        for j, kwd_group in enumerate(kwd_groups):
            if j in used:
                continue
            if _node_lang(kwd_group) == lang:
                assigned[i] = kwd_group
                used.add(j)
                break
    remaining_kwd = [group for j, group in enumerate(kwd_groups) if j not in used]
    for i, _abstract in enumerate(abstracts):
        if assigned[i] is None and remaining_kwd:
            assigned[i] = remaining_kwd.pop(0)
    for i, abstract in enumerate(abstracts):
        label = _text(abstract.find("title"))
        if not label:
            lang = _node_lang(abstract)
            label = f"Abstract ({lang})" if lang else "Abstract"
        parts.append(
            format_html(
                "<section class='articleSection'>"
                "<h2 class='articleSectionTitle'>{}</h2>",
                label,
            )
        )
        for paragraph in abstract.findall(".//p"):
            parts.append(format_html("<p class='paragraph'>{}</p>", _text(paragraph)))
        if assigned[i] is not None:
            parts.append(_kwd_group_html(assigned[i]))
        parts.append(_static_html("</section>"))
    for kwd_group in remaining_kwd:
        parts.append(_kwd_group_html(kwd_group))
    history = root.find(".//history")
    if history is not None:
        date_labels = {
            "received": gettext("Received"),
            "rev-request": gettext("Revision requested"),
            "rev-recd": gettext("Revised"),
            "accepted": gettext("Accepted"),
        }
        items = []
        for date in history.findall("date"):
            date_type = date.get("date-type") or ""
            day = _text(date.find("day"))
            month = _text(date.find("month"))
            year = _text(date.find("year"))
            if month.isdigit():
                month_num = int(month)
                if month_num in MONTHS:
                    month = str(MONTHS[month_num])
            value = " ".join(part for part in (day, month, year) if part)
            if date_type and value:
                items.append((date_labels.get(date_type, date_type), value))
        if items:
            parts.append(_timeline_section(gettext("History"), items))
    counts = root.find(".//counts")
    if counts is not None:
        count_labels = (
            ("fig-count", gettext("Figures")),
            ("table-count", gettext("Tables")),
            ("equation-count", gettext("Equations")),
            ("ref-count", gettext("References")),
        )
        items = []
        for tag, label in count_labels:
            element = counts.find(tag)
            if element is not None and element.get("count") is not None:
                items.append((label, element.get("count")))
        if items:
            parts.append(_timeline_section(gettext("Counts"), items))
    if not parts:
        parts.append(format_html("<pre>{}</pre>", html.escape(marked_xml[:2000])))
    return _join_html(parts)


def render_body_preview(marked_xml, figure_urls=None):
    if not (marked_xml or "").strip():
        return format_html(
            "<p class='alert alert-info'>{}</p>", gettext("No body markup yet.")
        )
    try:
        root = etree.fromstring(marked_xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return format_html(
            "<p class='alert alert-danger'>{}</p>", gettext("Invalid body XML.")
        )
    parts = []
    for sec in root.findall(".//sec"):
        title = _text(sec.find("title"))
        parts.append(_static_html("<section class='articleSection'>"))
        if title:
            parts.append(format_html("<h2 class='articleSectionTitle'>{}</h2>", title))
        for child in sec:
            if child.tag == "p":
                parts.append(format_html("<p class='paragraph'>{}</p>", _text(child)))
            elif child.tag in ("fig", "fig-group"):
                figs = [child] if child.tag == "fig" else child.findall("fig")
                for fig in figs:
                    parts.append(_render_fig_preview(fig, figure_urls))
            elif child.tag == "table-wrap":
                table_parts = [
                    format_html(
                        "<p><strong>{}</strong> {}</p>",
                        _text(child.find("label")),
                        _text(child.find("caption")),
                    )
                ]
                table = child.find("table")
                if table is not None:
                    chunks = []
                    thead = table.find("thead")
                    tbody = table.find("tbody")
                    if thead is not None:
                        chunks.append(_jats_table_section_html(thead, "thead", True))
                    if tbody is not None:
                        chunks.append(_jats_table_section_html(tbody, "tbody", False))
                    elif thead is None:
                        chunks.append(_jats_table_section_html(table, "tbody", False))
                    table_parts.append(
                        format_html(
                            "<table class='table table-hover'>{}</table>",
                            _join_html(chunks),
                        )
                    )
                attrib = _text(child.find("attrib"))
                if attrib:
                    table_parts.append(
                        format_html("<p class='paragraph'>{}</p>", attrib)
                    )
                foot = child.find("table-wrap-foot")
                if foot is not None:
                    for fn in foot.findall("fn"):
                        table_parts.append(
                            format_html("<p class='paragraph'>{}</p>", _text(fn))
                        )
                parts.append(
                    format_html(
                        "<div class='table'>{}</div>",
                        _join_html(table_parts),
                    )
                )
        parts.append(_static_html("</section>"))
    if not parts:
        parts.append(format_html("<pre>{}</pre>", html.escape(marked_xml[:2000])))
    return _join_html(parts)


def render_back_preview(references):
    if not references:
        return format_html(
            "<p class='alert alert-info'>{}</p>",
            gettext("No references marked yet."),
        )
    parts = [
        format_html(
            '<section class="articleSection ref-list">'
            '<h2 class="articleSectionTitle">{}</h2><ol class="refList">',
            gettext("References"),
        )
    ]
    for ref in references:
        parts.append(format_html("<li>{}</li>", ref.mixed_citation or ""))
    parts.append(_static_html("</ol></section>"))
    return _join_html(parts)


def _article_language(assembled_xml, language):
    if (language or "").strip():
        return language.strip()[:2]
    stripped = re.sub(r"<!DOCTYPE[^>]+>", "", assembled_xml or "", count=1)
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError:
        return "en"
    xml_lang = root.get("{http://www.w3.org/XML/1998/namespace}lang") or ""
    return (xml_lang.strip() or "en")[:2]


def _packtools_article_txt_html(html_document):
    nodes = html_document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' articleTxt ')]"
    )
    if not nodes:
        return None
    node = nodes[0]
    return format_html(
        "{}",
        SafeString(
            "".join(
                etree.tostring(child, encoding="unicode", method="html")
                for child in node
            )
        ),
    )


def apply_figure_urls(html_content, figure_urls, xml_text=None):
    text = str(html_content or "")
    for href, url in figure_urls.items():
        if href and url and href in text:
            text = text.replace(href, url)
    if not figure_urls or not (xml_text or "").strip() or "thumbOff" not in text:
        return SafeString(text)
    stripped = re.sub(r"<!DOCTYPE[^>]+>", "", xml_text, count=1)
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError:
        return SafeString(text)
    document = lhtml.fromstring(f"<div>{text}</div>")
    for fig in root.findall(".//fig"):
        fig_id = (fig.get("id") or "").strip()
        graphic = fig.find("graphic")
        href = (graphic.get(XLINK_HREF) or "").strip() if graphic is not None else ""
        url = figure_urls.get(href)
        if not fig_id or not url:
            continue
        nodes = document.xpath(f'//*[@id="{fig_id}"]//*[contains(@class, "thumbOff")]')
        if not nodes or nodes[0].find(".//img") is not None:
            continue
        img = lhtml.Element("img")
        img.set("src", url)
        img.set("alt", fig_id)
        nodes[0].insert(0, img)
    return SafeString(
        "".join(
            etree.tostring(child, encoding="unicode", method="html")
            for child in document
        )
    )


def preview_article_xml(manuscript, part):
    from manuscript.services.marking import build_manuscript_ref_list_xml
    from xml_manager.assembly import generate_xml_sps

    if part == "article" and (manuscript.assembled_xml or "").strip():
        return manuscript.assembled_xml
    front = (manuscript.front_marked_xml or "").strip()
    body = (manuscript.body_marked_xml or "").strip()
    back = ""
    if part in ("back", "article"):
        back = (build_manuscript_ref_list_xml(manuscript) or "").strip()
    required = {
        "front": front,
        "body": body,
        "back": back,
        "article": front or body or back,
    }
    if part not in required or not required[part]:
        raise ManuscriptPreviewError("empty")
    try:
        return generate_xml_sps(
            front or "<front/>",
            body or "<body/>",
            back or "<back/>",
            article_type=manuscript.article_type,
            language=manuscript.language or None,
            specific_use=manuscript.specific_use,
        )
    except ValueError as exc:
        raise ManuscriptPreviewError("invalid xml") from exc


def render_article_preview_packtools(assembled_xml, language=None):
    if not (assembled_xml or "").strip():
        raise ManuscriptPreviewError("empty")
    stripped = re.sub(r"<!DOCTYPE[^>]+>", "", assembled_xml, count=1)
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ManuscriptPreviewError("invalid xml") from exc
    lang = _article_language(assembled_xml, language)
    tree = etree.ElementTree(root)
    try:
        generator = HTMLGenerator.parse(tree, valid_only=False)
        html_root = generator.generate(lang)
        full_html = etree.tostring(html_root, encoding="unicode", method="html")
    except Exception as exc:
        raise ManuscriptPreviewError("packtools generation failed") from exc
    try:
        document = lhtml.fromstring(full_html.encode("utf-8"))
    except etree.ParserError as exc:
        raise ManuscriptPreviewError("packtools html parse failed") from exc
    content = _packtools_article_txt_html(document)
    if content is None:
        raise ManuscriptPreviewError("packtools article body missing")
    return content


def render_article_preview(assembled_xml, figure_urls=None):
    if not (assembled_xml or "").strip():
        return format_html(
            "<p class='alert alert-info'>{}</p>",
            gettext("No assembled XML yet."),
        )
    stripped = re.sub(r"<!DOCTYPE[^>]+>", "", assembled_xml, count=1)
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError:
        return format_html(
            "<p class='alert alert-danger'>{}</p>",
            gettext("Invalid article XML."),
        )
    front = root.find("front")
    body = root.find("body")
    back = root.find("back")
    parts = []
    if front is not None:
        parts.append(render_front_preview(etree.tostring(front, encoding="unicode")))
    if body is not None:
        parts.append(
            render_body_preview(
                etree.tostring(body, encoding="unicode"),
                figure_urls=figure_urls,
            )
        )
    if back is not None:
        ref_items = []
        for ref in back.findall(".//ref"):
            mixed = ref.find("mixed-citation")

            class Ref:
                mixed_citation = _text(mixed)

            ref_items.append(Ref())
        parts.append(render_back_preview(ref_items))
    return _join_html(parts)
