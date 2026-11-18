import logging
import os
import re
import tempfile
import zipfile

from lxml import etree

from front.utils import (
    FIGURE_CAPTION_RE,
    HISTORY_LINE_RE,
    PUBLICATION_HISTORY_RE,
    TABLE_CAPTION_RE,
    reference_run_start_index,
)
from reference.exceptions import DocxReferencesError

logger = logging.getLogger(__name__)

REFERENCE_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:references?|referências?|referencias?|"
    r"bibliography|bibliografia)\s*$",
    re.IGNORECASE,
)
REFERENCE_TAIL_RE = re.compile(
    r"^(?:figures?\s+captions?|legendas?(?:\s+das\s+figuras)?|figuras)\s*:?\s*$",
    re.IGNORECASE,
)


def stz_norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def parse_reference_list(references):
    if references is None:
        return []
    if isinstance(references, str):
        return [line.strip() for line in references.split("\n") if line.strip()]
    if isinstance(references, (list, tuple)):
        return [str(item).strip() for item in references if str(item).strip()]
    text = str(references).strip()
    return [text] if text else []


def extract_references_section(text):
    if not text:
        return ""
    lines = str(text).split("\n")
    start = None
    for index, line in enumerate(lines):
        if REFERENCE_HEADING_RE.match(line.strip()):
            start = index + 1
            break
    if start is None:
        start = reference_run_start_index(lines)
    if start is None:
        return ""
    kept = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if (
            HISTORY_LINE_RE.match(stripped)
            or PUBLICATION_HISTORY_RE.match(stripped)
            or FIGURE_CAPTION_RE.match(stripped)
            or TABLE_CAPTION_RE.match(stripped)
            or REFERENCE_TAIL_RE.match(stripped)
        ):
            break
        kept.append(stripped)
    return "\n".join(kept)


def extract_text_from_docx(docx_path, limit_chars=30000):
    logger.info("Text extractor: using zipfile for %s", os.path.basename(docx_path))
    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = etree.fromstring(xml_bytes)
    nsmap = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paragraphs = []
    for paragraph in root.xpath("//w:p | //w:tc//w:p", namespaces=nsmap):
        text = "".join(
            t.text or "" for t in paragraph.xpath(".//w:t", namespaces=nsmap)
        )
        text = text.strip()
        if text:
            paragraphs.append(text)

    result = "\n".join(paragraphs)
    if limit_chars is not None:
        result = result[:limit_chars]
    logger.info("Text extractor: zipfile produced %d chars", len(result))
    return result


def references_from_docx_upload(uploaded):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        text = extract_text_from_docx(tmp_path, limit_chars=None)
    except Exception as exc:
        raise DocxReferencesError("Could not read DOCX file") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    references = extract_references_section(text)
    if not parse_reference_list(references):
        raise DocxReferencesError("No references section found in DOCX")
    return references
