import io
import os
import re
import shutil
import tempfile
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from docx import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from lxml import etree
from packtools.sps.formats.pdf.pipeline import docx as packtools_docx
from packtools.sps.formats.pdf.renderer.docx import table as packtools_table
from packtools.sps.formats.pdf.utils import file_utils as packtools_file_utils
from packtools.sps.utils import xml_utils as packtools_xml_utils
from wagtail.documents.models import Document

from manuscript.services.marking import build_manuscript_ref_list_xml
from xml_manager.assembly import generate_xml_sps


class AssemblyError(Exception):
    pass


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _xml_text(root, path):
    node = root.find(path)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _pad_numeric(value):
    text = (value or "").strip()
    if text.isdigit():
        return text.zfill(2)
    return text


def _doi_suffix(doi):
    text = (doi or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    if text.lower().startswith("doi.org/"):
        text = text.split("/", 1)[1]
    if "/" in text:
        return text.split("/", 1)[1]
    return text


def _acronym_from_journal_title(title):
    words = re.findall(r"[0-9A-Za-zÀ-ÿ]+", title or "")
    skipped = {
        "de",
        "da",
        "do",
        "dos",
        "das",
        "e",
        "of",
        "the",
        "and",
        "del",
        "la",
        "el",
    }
    words = [word for word in words if word.lower() not in skipped]
    if not words:
        return ""
    if len(words) == 1:
        return re.sub(r"[^a-z0-9]", "", words[0].lower())[:12]
    return "".join(word[0] for word in words).lower()


def _acronym_from_manuscript(manuscript):
    from front.data_utils import journal_acronym_from_text

    marked = manuscript.front_marked
    if not isinstance(marked, dict):
        marked = {}
    journal = marked.get("journal") if isinstance(marked.get("journal"), dict) else {}
    for item in journal.get("journal_ids") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "publisher-id":
            continue
        value = str(item.get("value") or "").strip()
        if value:
            return value
    return journal_acronym_from_text(manuscript.front_source_text)


def sps_package_stem(xml_text, acronym=""):
    stripped = xml_text or ""
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise AssemblyError(_("Assembled XML is invalid")) from exc
    issn = (
        _xml_text(root, './/issn[@pub-type="epub"]')
        or _xml_text(root, './/issn[@pub-type="ppub"]')
        or _xml_text(root, ".//issn")
    )
    acronym = (
        _xml_text(root, './/journal-id[@journal-id-type="publisher-id"]')
        or (acronym or "").strip()
    )
    if not acronym:
        acronym = _acronym_from_journal_title(
            _xml_text(root, ".//abbrev-journal-title")
            or _xml_text(root, ".//journal-title")
        )
    missing = []
    if not issn:
        missing.append("ISSN")
    if not acronym:
        missing.append("acronym")
    if missing:
        raise AssemblyError(
            _("SPS package name is missing %(fields)s") % {"fields": ", ".join(missing)}
        )
    volume = _xml_text(root, ".//article-meta/volume")
    issue = _xml_text(root, ".//article-meta/issue")
    fpage = _xml_text(root, ".//article-meta/fpage")
    elocation = _xml_text(root, ".//article-meta/elocation-id")
    parts = [issn, acronym]
    if volume or issue:
        if volume:
            parts.append(_pad_numeric(volume))
        if issue:
            parts.append(_pad_numeric(issue))
        page = fpage or elocation
        if not page:
            raise AssemblyError(_("SPS package name is missing pagination"))
        parts.append(page)
    else:
        doi = _doi_suffix(_xml_text(root, './/article-id[@pub-id-type="doi"]'))
        if not doi:
            raise AssemblyError(_("SPS package name is missing DOI"))
        parts.append(doi)
    return "-".join(parts)


def _graphic_href(graphic):
    for key, value in graphic.attrib.items():
        if key == "href" or key.endswith("}href"):
            return (value or "").strip()
    return ""


def _figure_extension(href):
    ext = os.path.splitext(href or "")[1].lower() or ".jpg"
    if ext == ".jpeg":
        return ".jpg"
    return ext


def package_xml_with_sps_names(xml_text, acronym=""):
    stem = sps_package_stem(xml_text, acronym=acronym)
    root = etree.fromstring(xml_text.encode("utf-8"))
    href_map = {}
    graphics = root.xpath(".//*[local-name()='fig']/*[local-name()='graphic']")
    for index, graphic in enumerate(graphics, start=1):
        old = _graphic_href(graphic)
        new_name = f"{stem}-gf{index:02d}{_figure_extension(old)}"
        if old:
            href_map[old] = new_name
        graphic.set(XLINK_HREF, new_name)
    packed = etree.tostring(root, encoding="unicode")
    return stem, packed, href_map


def _figure_for_href(figures, old_href, index):
    base = os.path.basename((old_href or "").replace("\\", "/"))
    by_href = {figure.href: figure for figure in figures}
    by_base = {
        os.path.basename(figure.href.replace("\\", "/")): figure for figure in figures
    }
    by_number = {figure.number: figure for figure in figures}
    figure = by_href.get(old_href) or by_href.get(base) or by_base.get(base)
    if figure is not None:
        return figure
    match = re.search(r"(\d+)", base)
    if match:
        figure = by_number.get(int(match.group(1)))
        if figure is not None:
            return figure
    return by_number.get(index)


_PACKTOOLS_PDF_PARAGRAPH_STYLES = (
    "SCL Abstract Title",
    "SCL Affiliation",
    "SCL Article Category",
    "SCL Article Title",
    "SCL Author",
    "SCL Footer",
    "SCL Header Paragraph",
    "SCL Paragraph",
    "SCL Paragraph Abstract",
    "SCL Paragraph Cite As",
    "SCL Paragraph Keywords",
    "SCL Paragraph Reference",
    "SCL Section Title",
    "SCL Subsection Title",
    "SCL Table Heading",
)
_PACKTOOLS_PDF_CHARACTER_STYLES = (
    "SCL Affiliation Char",
    "SCL Author Char",
    "SCL Header Paragraph Char",
    "SCL Journal Title Char",
    "SCL Paragraph Cite As Char",
    "SCL Paragraph Cite As Footer Char",
    "SCL Paragraph Cite As Journal Title Char",
    "SCL Paragraph Keywords Char",
    "SCL Paragraph Keywords Header Char",
)


def assemble_manuscript_xml(manuscript):
    if not (manuscript.front_marked_xml or "").strip():
        raise AssemblyError(_("Front XML is missing"))
    if not (manuscript.body_marked_xml or "").strip():
        raise AssemblyError(_("Body XML is missing"))
    back_xml = build_manuscript_ref_list_xml(manuscript)
    if not back_xml.strip():
        raise AssemblyError(_("Reference list XML is missing"))
    xml = generate_xml_sps(
        manuscript.front_marked_xml,
        manuscript.body_marked_xml,
        back_xml,
        article_type=manuscript.article_type,
        language=manuscript.language or None,
        specific_use=manuscript.specific_use,
    )
    manuscript.assembled_xml = xml
    manuscript.save(update_fields=["assembled_xml", "updated"])
    return xml


def refresh_assembled_xml(manuscript):
    if not (manuscript.front_marked_xml or "").strip():
        return None
    if not (manuscript.body_marked_xml or "").strip():
        return None
    back_xml = build_manuscript_ref_list_xml(manuscript)
    if not back_xml.strip():
        return None
    return assemble_manuscript_xml(manuscript)


def generate_packtools_pdf(xml_text, xml_name, figures):
    tmp = tempfile.mkdtemp(prefix="sps-pdf-")
    try:
        xml_path = os.path.join(tmp, xml_name)
        with open(xml_path, "w", encoding="utf-8") as fh:
            fh.write(xml_text)
        for figure in figures:
            dest = os.path.join(tmp, figure.href)
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with figure.file.open("rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
        layout = (getattr(settings, "PACKTOOLS_PDF_LAYOUT", "") or "").strip()
        if layout and os.path.isfile(layout):
            base_layout = layout
        else:
            base_layout = os.path.join(tmp, "_scielo-layout.docx")
            layout_doc = DocxDocument()
            for name in _PACKTOOLS_PDF_PARAGRAPH_STYLES:
                if name not in layout_doc.styles:
                    layout_doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            for name in _PACKTOOLS_PDF_CHARACTER_STYLES:
                if name not in layout_doc.styles:
                    layout_doc.styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
            layout_doc.save(base_layout)
        xml_tree = packtools_xml_utils.get_xml_tree(xml_path)
        original_num_cols = packtools_table._determine_num_cols
        original_merge = packtools_table._merge_horizontally

        def determine_num_cols(headers, rows, header_spans, row_spans):
            widths = []
            for group in (header_spans, row_spans, headers, rows):
                if group:
                    widths.append(max(len(row) for row in group))
            return max(widths) if widths else 0

        def merge_horizontally(row, start_col, span, num_cols, is_header=False):
            if start_col < 0 or start_col >= len(row.cells):
                return None
            return original_merge(row, start_col, span, num_cols, is_header=is_header)

        packtools_table._determine_num_cols = determine_num_cols
        packtools_table._merge_horizontally = merge_horizontally
        try:
            document = packtools_docx.pipeline_docx(
                xml_tree,
                {
                    "base_layout": base_layout,
                    "assets_dir": tmp,
                },
            )
        finally:
            packtools_table._determine_num_cols = original_num_cols
            packtools_table._merge_horizontally = original_merge
        stem, _ext = os.path.splitext(xml_name)
        docx_path = os.path.join(tmp, f"{stem}.docx")
        document.save(docx_path)
        binary = (getattr(settings, "LIBREOFFICE_BINARY", "") or "").strip()
        if binary:
            pdf_path = packtools_file_utils.convert_docx_to_pdf(docx_path, binary)
        else:
            pdf_path = packtools_file_utils.convert_docx_to_pdf(docx_path)
        with open(pdf_path, "rb") as fh:
            return fh.read()
    except AssemblyError:
        raise
    except Exception as exc:
        raise AssemblyError(_("PDF generation failed: %s") % exc) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_sps_zip(manuscript, include_pdf=False):
    if not (manuscript.assembled_xml or "").strip():
        assemble_manuscript_xml(manuscript)
    pdf_bytes = None
    if include_pdf:
        pdf_bytes = generate_packtools_pdf(
            manuscript.assembled_xml,
            "article.xml",
            list(manuscript.figure_files.all()),
        )
    stem, packed_xml, href_map = package_xml_with_sps_names(
        manuscript.assembled_xml,
        acronym=_acronym_from_manuscript(manuscript),
    )
    figures = list(manuscript.figure_files.all().order_by("number"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{stem}.xml", packed_xml.encode("utf-8"))
        written = set()
        for index, (old_href, new_name) in enumerate(href_map.items(), start=1):
            figure = _figure_for_href(figures, old_href, index)
            if figure is None or figure.pk in written:
                continue
            with figure.file.open("rb") as fh:
                archive.writestr(new_name, fh.read())
            written.add(figure.pk)
        for figure in figures:
            if figure.pk in written:
                continue
            name = f"{stem}-gf{figure.number:02d}{_figure_extension(figure.href)}"
            with figure.file.open("rb") as fh:
                archive.writestr(name, fh.read())
        if pdf_bytes is not None:
            archive.writestr(f"{stem}.pdf", pdf_bytes)
    buffer.seek(0)
    zip_name = f"{stem}.zip"
    if manuscript.sps_package_id:
        if manuscript.sps_package.file:
            manuscript.sps_package.file.delete(save=False)
        manuscript.sps_package.file.save(
            zip_name, ContentFile(buffer.read()), save=True
        )
        manuscript.sps_package.title = zip_name
        manuscript.sps_package.save()
        document = manuscript.sps_package
    else:
        document = Document(title=zip_name)
        buffer.seek(0)
        document.file.save(zip_name, ContentFile(buffer.read()), save=True)
        manuscript.sps_package = document
        manuscript.save(update_fields=["sps_package", "updated"])
    return document
