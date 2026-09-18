import io
import os
import shutil
import tempfile
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from docx import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from packtools.sps.formats.pdf.pipeline import docx as packtools_docx
from packtools.sps.formats.pdf.renderer.docx import table as packtools_table
from packtools.sps.formats.pdf.utils import file_utils as packtools_file_utils
from packtools.sps.utils import xml_utils as packtools_xml_utils
from wagtail.documents.models import Document

from manuscript.services.marking import build_manuscript_ref_list_xml
from xml_manager.assembly import generate_xml_sps


class AssemblyError(Exception):
    pass


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
    slug = "".join(ch if ch.isalnum() else "-" for ch in manuscript.title[:40]).strip(
        "-"
    )
    if not slug:
        slug = f"manuscript-{manuscript.pk}"
    xml_name = f"{slug}.xml"
    pdf_bytes = None
    if include_pdf:
        pdf_bytes = generate_packtools_pdf(
            manuscript.assembled_xml,
            xml_name,
            list(manuscript.figure_files.all()),
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(xml_name, manuscript.assembled_xml.encode("utf-8"))
        for figure in manuscript.figure_files.all():
            with figure.file.open("rb") as fh:
                archive.writestr(figure.href, fh.read())
        if pdf_bytes is not None:
            archive.writestr(f"{slug}.pdf", pdf_bytes)
    buffer.seek(0)
    zip_name = f"{slug}.zip"
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
