import os
import re
import tempfile
import zipfile

from lxml import etree

from front.exceptions import FrontDocxError

BODY_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"introduction|introdução|introducao|introducción|introduccion|"
    r"methods?|metodologia|metodología|methodology|"
    r"materials?(?:\s+and\s+methods?)?|"
    r"material(?:es)?(?:\s+y\s+métodos)?|"
    r"results?|resultados|"
    r"discussion|discussão|discusion|"
    r"conclus(?:ion|ões|iones)?"
    r")\s*$",
    re.IGNORECASE,
)

FRONT_CHAR_LIMIT = 12000


def normalize_front_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def extract_text_from_docx(docx_path):
    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = etree.fromstring(xml_bytes)
    nsmap = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paragraphs = []
    for paragraph in root.xpath("//w:p", namespaces=nsmap):
        text = "".join(
            node.text or "" for node in paragraph.xpath(".//w:t", namespaces=nsmap)
        )
        text = text.strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_front_section(text):
    if not text:
        return ""
    lines = str(text).split("\n")
    cut = None
    for index, line in enumerate(lines):
        if BODY_HEADING_RE.match(line.strip()):
            cut = index
            break
    selected = lines[:cut] if cut is not None else lines
    result = "\n".join(line.strip() for line in selected if line.strip())
    if cut is None:
        result = result[:FRONT_CHAR_LIMIT]
    return result


def front_from_docx_upload(uploaded):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        text = extract_text_from_docx(tmp_path)
    except Exception as exc:
        raise FrontDocxError("Could not read DOCX file") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    front_text = extract_front_section(text)
    if not front_text.strip():
        raise FrontDocxError("No front section found in DOCX")
    return front_text
