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
from docx.shared import Pt
from lxml import etree
from packtools.sps.formats.pdf.convert import convert_docx_to_pdf
from packtools.sps.formats.pdf.pipeline import pipeline_docx_by_language
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


def sps_package_stem(xml_text, acronym="", fallback_stem=""):
    stripped = xml_text or ""
    try:
        root = etree.fromstring(stripped.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        if fallback_stem:
            return fallback_stem
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
        if fallback_stem:
            return fallback_stem
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
            if fallback_stem:
                return fallback_stem
            raise AssemblyError(_("SPS package name is missing pagination"))
        parts.append(page)
    else:
        doi = _doi_suffix(_xml_text(root, './/article-id[@pub-id-type="doi"]'))
        if not doi:
            if fallback_stem:
                return fallback_stem
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


def package_xml_with_sps_names(xml_text, acronym="", fallback_stem=""):
    stem = sps_package_stem(xml_text, acronym=acronym, fallback_stem=fallback_stem)
    root = etree.fromstring(xml_text.encode("utf-8"))
    renames = []
    graphics = root.xpath(".//*[local-name()='fig']/*[local-name()='graphic']")
    for index, graphic in enumerate(graphics, start=1):
        old = _graphic_href(graphic)
        new_name = f"{stem}-gf{index:02d}{_figure_extension(old)}"
        graphic.set(XLINK_HREF, new_name)
        renames.append((old, new_name, index))
    packed = etree.tostring(root, encoding="unicode")
    return stem, packed, renames


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
    for number in reversed([int(item) for item in re.findall(r"(\d+)", base)]):
        figure = by_number.get(number)
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


def assemble_manuscript_xml(manuscript, allow_partial=False):
    front_xml = (manuscript.front_marked_xml or "").strip()
    body_xml = (manuscript.body_marked_xml or "").strip()
    back_xml = (build_manuscript_ref_list_xml(manuscript) or "").strip()
    if not allow_partial:
        if not front_xml:
            raise AssemblyError(_("Front XML is missing"))
        if not body_xml:
            raise AssemblyError(_("Body XML is missing"))
        if not back_xml:
            raise AssemblyError(_("Reference list XML is missing"))
    elif not (front_xml or body_xml or back_xml):
        raise AssemblyError(_("Front XML is missing"))
    xml = generate_xml_sps(
        front_xml or "<front/>",
        body_xml or "<body/>",
        back_xml or "<back/>",
        article_type=manuscript.article_type,
        language=manuscript.language or None,
        specific_use=manuscript.specific_use,
    )
    manuscript.assembled_xml = xml
    manuscript.save(update_fields=["assembled_xml", "updated"])
    return xml


def refresh_assembled_xml(manuscript, allow_partial=False):
    if not allow_partial:
        if not (manuscript.front_marked_xml or "").strip():
            return None
        if not (manuscript.body_marked_xml or "").strip():
            return None
        back_xml = build_manuscript_ref_list_xml(manuscript)
        if not back_xml.strip():
            return None
        return assemble_manuscript_xml(manuscript)
    try:
        return assemble_manuscript_xml(manuscript, allow_partial=True)
    except AssemblyError, ValueError:
        return None


def generate_packtools_pdf(xml_text, xml_name, figures):
    tmp = tempfile.mkdtemp(prefix="sps-pdf-")
    try:
        figures = list(figures)
        asset_hrefs = []
        stripped_xml = re.sub(r"<!DOCTYPE[^>]+>", "", xml_text, count=1)
        try:
            asset_root = etree.fromstring(stripped_xml.encode("utf-8"))
        except etree.XMLSyntaxError:
            asset_root = None
        if asset_root is not None:
            graphics = asset_root.xpath(
                ".//*[local-name()='graphic' or local-name()='inline-graphic']"
            )
            for index, graphic in enumerate(graphics, start=1):
                href = _graphic_href(graphic)
                if (
                    not href
                    or href.startswith(("http://", "https://"))
                    or os.path.isabs(href)
                ):
                    continue
                figure = _figure_for_href(figures, href, index)
                if figure is not None:
                    asset_hrefs.append((href, figure))
        for figure in figures:
            if figure.href:
                asset_hrefs.append((figure.href, figure))
        written_assets = set()
        for href, figure in asset_hrefs:
            if not figure.image_id or not figure.image or not figure.image.file:
                continue
            relative = href.replace("\\", "/").split("?")[0].split("#")[0].lstrip("/")
            if not relative or relative.startswith("..") or "/../" in f"/{relative}":
                continue
            dest = os.path.normpath(os.path.join(tmp, relative))
            root_dir = os.path.normpath(tmp)
            if os.path.commonpath([dest, root_dir]) != root_dir:
                continue
            asset_key = (dest, figure.pk)
            if asset_key in written_assets:
                continue
            written_assets.add(asset_key)
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with figure.image.file.open("rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
        xml_path = os.path.join(tmp, xml_name)
        with open(xml_path, "w", encoding="utf-8") as fh:
            fh.write(xml_text)
        layout = (getattr(settings, "PACKTOOLS_PDF_LAYOUT", "") or "").strip()
        if layout and os.path.isfile(layout):
            base_layout = layout
        else:
            base_layout = os.path.join(tmp, "_scielo-layout.docx")
            layout_doc = DocxDocument()
            for name in _PACKTOOLS_PDF_PARAGRAPH_STYLES:
                if name not in layout_doc.styles:
                    style = layout_doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
                    if name == "SCL Paragraph":
                        style.font.size = Pt(10)
            for name in _PACKTOOLS_PDF_CHARACTER_STYLES:
                if name not in layout_doc.styles:
                    layout_doc.styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
            layout_doc.save(base_layout)
        xml_tree = packtools_xml_utils.get_xml_tree(xml_path)
        if isinstance(xml_tree, etree._Element | etree._ElementTree):
            root_el = (
                xml_tree.getroot()
                if isinstance(xml_tree, etree._ElementTree)
                else xml_tree
            )
            if not root_el.get("article-type"):
                root_el.set("article-type", "research-article")
            if not root_el.get("{http://www.w3.org/XML/1998/namespace}lang"):
                root_el.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
            front_el = root_el.find("front")
            if front_el is None:
                front_el = etree.SubElement(root_el, "front")
            if root_el.find(".//journal-title") is None:
                jm = front_el.find("journal-meta")
                if jm is None:
                    jm = etree.SubElement(front_el, "journal-meta")
                jtg = jm.find("journal-title-group")
                if jtg is None:
                    jtg = etree.SubElement(jm, "journal-title-group")
                etree.SubElement(jtg, "journal-title").text = ""
            am = front_el.find("article-meta")
            if am is None:
                am = etree.SubElement(front_el, "article-meta")
            if root_el.find('.//article-id[@pub-id-type="doi"]') is None:
                doi_el = etree.SubElement(
                    am, "article-id", attrib={"pub-id-type": "doi"}
                )
                doi_el.text = ""
            heading_xpath = './/subj-group[@subj-group-type="heading"]/subject'
            if root_el.find(heading_xpath) is None:
                ac = am.find("article-categories")
                if ac is None:
                    ac = etree.SubElement(am, "article-categories")
                sg = etree.SubElement(
                    ac, "subj-group", attrib={"subj-group-type": "heading"}
                )
                etree.SubElement(sg, "subject").text = ""
            if root_el.find(".//article-title") is None:
                tg = am.find("title-group")
                if tg is None:
                    tg = etree.SubElement(am, "title-group")
                etree.SubElement(tg, "article-title").text = ""
        _lang, document = next(
            iter(
                pipeline_docx_by_language(
                    xml_tree,
                    {
                        "base_layout": base_layout,
                        "assets_dir": tmp,
                    },
                )
            )
        )
        stem, _ext = os.path.splitext(xml_name)
        docx_path = os.path.join(tmp, f"{stem}.docx")
        document.save(docx_path)
        binary = (getattr(settings, "LIBREOFFICE_BINARY", "") or "").strip() or None
        pdf_path = convert_docx_to_pdf(docx_path, binary)
        with open(pdf_path, "rb") as fh:
            return fh.read()
    except AssemblyError:
        raise
    except Exception as exc:
        raise AssemblyError(_("PDF generation failed: %s") % exc) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _save_or_replace_manuscript_document(
    manuscript, attr_name, filename, content_bytes
):
    doc = getattr(manuscript, attr_name, None)
    if getattr(manuscript, f"{attr_name}_id", None) and doc is not None:
        if doc.file:
            doc.file.delete(save=False)
        doc.file.save(filename, ContentFile(content_bytes), save=True)
        doc.title = filename
        doc.save()
        return doc
    doc = Document(title=filename)
    doc.file.save(filename, ContentFile(content_bytes), save=True)
    setattr(manuscript, attr_name, doc)
    manuscript.save(update_fields=[attr_name, "updated"])
    return doc


def build_sps_zip(
    manuscript, include_pdf=False, allow_fallback_stem=False, pdf_bytes=None
):
    if not (manuscript.assembled_xml or "").strip():
        assemble_manuscript_xml(manuscript, allow_partial=allow_fallback_stem)
    fallback_stem = (
        f"manuscript-{manuscript.pk or 'draft'}" if allow_fallback_stem else ""
    )
    if manuscript.pk:
        figures = list(
            manuscript.figure_files.model.objects.filter(manuscript_id=manuscript.pk)
            .select_related("image")
            .order_by("number", "pk")
        )
    else:
        figures = list(
            manuscript.figure_files.select_related("image").order_by("number")
        )
    if include_pdf:
        pdf_bytes = generate_packtools_pdf(
            manuscript.assembled_xml,
            "article.xml",
            figures,
        )
    elif pdf_bytes is None and manuscript.pk:
        stored = (
            type(manuscript)
            .objects.filter(pk=manuscript.pk)
            .select_related("generated_pdf")
            .first()
        )
        pdf_doc = stored.generated_pdf if stored is not None else None
        if pdf_doc is not None and pdf_doc.file:
            try:
                with pdf_doc.file.open("rb") as pdf_fh:
                    pdf_bytes = pdf_fh.read()
            except OSError:
                pdf_bytes = None
    stem, packed_xml, renames = package_xml_with_sps_names(
        manuscript.assembled_xml,
        acronym=_acronym_from_manuscript(manuscript),
        fallback_stem=fallback_stem,
    )
    if include_pdf and pdf_bytes is not None:
        _save_or_replace_manuscript_document(
            manuscript, "generated_pdf", f"{stem}.pdf", pdf_bytes
        )
    used = set()
    slots = []
    for old_href, new_name, index in renames:
        available = [figure for figure in figures if figure.pk not in used]
        figure = _figure_for_href(available, old_href, index)
        if figure is not None:
            used.add(figure.pk)
        slots.append([new_name, figure])
    for slot in slots:
        if slot[1] is not None:
            continue
        remaining = [figure for figure in figures if figure.pk not in used]
        if not remaining:
            break
        slot[1] = remaining[0]
        used.add(remaining[0].pk)
    entries = [(name, figure) for name, figure in slots if figure is not None]
    for figure in figures:
        if figure.pk in used:
            continue
        entries.append(
            (
                f"{stem}-gf{figure.number:02d}{_figure_extension(figure.href)}",
                figure,
            )
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{stem}.xml", packed_xml.encode("utf-8"))
        written_names = set()
        for name, figure in entries:
            if (
                name in written_names
                or not figure.image_id
                or not figure.image
                or not figure.image.file
            ):
                continue
            with figure.image.file.open("rb") as fh:
                payload = fh.read()
            archive.writestr(name, payload)
            written_names.add(name)
        if pdf_bytes:
            archive.writestr(f"{stem}.pdf", pdf_bytes)
    buffer.seek(0)
    zip_name = f"{stem}.zip"
    return _save_or_replace_manuscript_document(
        manuscript, "sps_package", zip_name, buffer.read()
    )


def generate_manuscript_pdf_document(manuscript):
    if not (manuscript.assembled_xml or "").strip():
        assemble_manuscript_xml(manuscript, allow_partial=True)
    fallback_stem = f"manuscript-{manuscript.pk or 'draft'}"
    stem = sps_package_stem(
        manuscript.assembled_xml,
        acronym=_acronym_from_manuscript(manuscript),
        fallback_stem=fallback_stem,
    )
    pdf_bytes = generate_packtools_pdf(
        manuscript.assembled_xml,
        "article.xml",
        list(manuscript.figure_files.select_related("image").all()),
    )
    doc = _save_or_replace_manuscript_document(
        manuscript, "generated_pdf", f"{stem}.pdf", pdf_bytes
    )
    build_sps_zip(
        manuscript,
        allow_fallback_stem=True,
        pdf_bytes=pdf_bytes,
    )
    return doc


def generate_manuscript_html_document(manuscript):
    from django.template.loader import render_to_string

    from manuscript.preview import (
        ManuscriptPreviewError,
        apply_figure_urls,
        figure_urls_for_manuscript,
        preview_article_xml,
        render_article_preview,
        render_article_preview_packtools,
    )

    if not (manuscript.assembled_xml or "").strip():
        assemble_manuscript_xml(manuscript, allow_partial=True)
    fallback_stem = f"manuscript-{manuscript.pk or 'draft'}"
    stem = sps_package_stem(
        manuscript.assembled_xml,
        acronym=_acronym_from_manuscript(manuscript),
        fallback_stem=fallback_stem,
    )
    figure_urls = figure_urls_for_manuscript(manuscript)
    article_xml = preview_article_xml(manuscript, "article")
    try:
        raw_html = render_article_preview_packtools(
            article_xml,
            language=manuscript.language,
        )
        preview_html = apply_figure_urls(
            raw_html,
            figure_urls,
            xml_text=article_xml,
        )
    except ManuscriptPreviewError:
        preview_html = render_article_preview(article_xml, figure_urls=figure_urls)
    rendered = render_to_string(
        "manuscript/article_preview_frame.html",
        {
            "manuscript": manuscript,
            "preview_html": preview_html,
            "part": "article",
        },
    )
    return _save_or_replace_manuscript_document(
        manuscript, "generated_html", f"{stem}.html", rendered.encode("utf-8")
    )
