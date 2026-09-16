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

ACK_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"acknowledg(?:e?ments?)?|agradecimentos?|"
    r"funding|financiamento"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

BACK_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"authors?'?\s+contributions?|"
    r"contribui[cç][aã]o\s+dos\s+autores|"
    r"conflicts?\s+of\s+interest|"
    r"conflitos?\s+de\s+interesses?|"
    r"references|refer[eê]ncias|"
    r"supplementary\s+material|"
    r"material\s+suplementar|"
    r"data\s+availability|"
    r"disponibilidade\s+de\s+dados|"
    r"ethics|associate\s+editor"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

HISTORY_LABELS = (
    "received|recebido|recibido|submitted|"
    "accepted|aceito|aceptado|aprovado|approved|"
    "revised|revisado"
)
HISTORY_LINE_RE = re.compile(
    rf"^({HISTORY_LABELS})\b",
    re.IGNORECASE,
)
HISTORY_LABEL_RE = re.compile(
    rf"(?<![A-Za-z])(?P<label>{HISTORY_LABELS})"
    r"(?:\s+for\s+publication)?"
    r"(?:\s+(?:on|em))?"
    r"\s*[:.]?\s*",
    re.IGNORECASE,
)

FIGURE_CAPTION_RE = re.compile(
    r"^(?:Figure|Figura|Fig\.?)\s*[:.]?\s*(\d+)",
    re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    r"^(?:Table|Tabela|Tabla|Cuadro|TABELA)\s*[:.]?\s*(\d+)",
    re.IGNORECASE,
)
EQUATION_LABEL_RE = re.compile(
    r"(?:Equation|Equa[cç][aã]o)\s*(\d+)\s*$",
    re.IGNORECASE,
)
REFERENCE_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:references?|referências?|referencias?|"
    r"bibliography|bibliografia)\s*$",
    re.IGNORECASE,
)
COUNTS_STOP_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"appendix|apêndice|apendice|anexo|"
    r"supplementary(?:\s+material)?|material\s+suplementar"
    r")\s*:?\s*$",
    re.IGNORECASE,
)
NUMBERED_REF_RE = re.compile(r"^(?:<[^>]+>)?(\d+)\s*[\.\)]\s*\S")
NEW_REF_RE = re.compile(
    r"^(?:(?:da|de|do|dos|das|del|van|von)\s+)?[A-ZÀ-Ý]",
)
REF_CONTINUATION_RE = re.compile(r"^(?:https?://|www\.|doi:|10\.\d{4,})")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
DOCX_NSMAP = {"w": W_NS, "m": M_NS}

FRONT_CHAR_LIMIT = 12000


def normalize_front_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def read_docx_document(docx_path):
    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = etree.fromstring(xml_bytes)
    paragraphs = []
    for paragraph in root.xpath("//w:p", namespaces=DOCX_NSMAP):
        text = "".join(
            node.text or "" for node in paragraph.xpath(".//w:t", namespaces=DOCX_NSMAP)
        )
        text = text.strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs), root


def extract_text_from_docx(docx_path):
    text, _root = read_docx_document(docx_path)
    return text


def document_counts(text, xml_root=None):
    lines = [line.strip() for line in str(text or "").split("\n") if line.strip()]
    figures = set()
    tables = set()
    equations = set()
    for line in lines:
        match = FIGURE_CAPTION_RE.match(line)
        if match:
            figures.add(match.group(1))
        match = TABLE_CAPTION_RE.match(line)
        if match:
            tables.add(match.group(1))
        match = EQUATION_LABEL_RE.search(line)
        if match:
            equations.add(match.group(1))
    n_equations = len(equations)
    if n_equations == 0 and xml_root is not None:
        for paragraph in xml_root.xpath("//w:p", namespaces=DOCX_NSMAP):
            if not paragraph.xpath(".//m:oMath", namespaces=DOCX_NSMAP):
                continue
            para_text = "".join(
                node.text or ""
                for node in paragraph.xpath(".//w:t", namespaces=DOCX_NSMAP)
            ).strip()
            if not para_text:
                n_equations += 1
    start = None
    for index, line in enumerate(lines):
        if REFERENCE_HEADING_RE.match(line):
            start = index + 1
    n_refs = 0
    if start is not None:
        block = []
        for line in lines[start:]:
            if (
                COUNTS_STOP_RE.match(line)
                or FIGURE_CAPTION_RE.match(line)
                or TABLE_CAPTION_RE.match(line)
            ):
                break
            block.append(line)
        numbers = []
        for line in block:
            match = NUMBERED_REF_RE.match(line)
            if match:
                numbers.append(int(match.group(1)))
        if numbers and len(numbers) >= max(3, len(block) // 3):
            n_refs = max(numbers)
        else:
            for line in block:
                if NEW_REF_RE.match(line) and not REF_CONTINUATION_RE.match(line):
                    n_refs += 1
    return {
        "fig_count": str(len(figures)),
        "table_count": str(len(tables)),
        "equation_count": str(n_equations),
        "ref_count": str(n_refs),
    }


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
    if cut is not None:
        extras = []
        index = cut
        while index < len(lines):
            stripped = lines[index].strip()
            if ACK_HEADING_RE.match(stripped):
                extras.append(stripped)
                index += 1
                while index < len(lines):
                    nxt = lines[index].strip()
                    if not nxt:
                        index += 1
                        continue
                    if (
                        BODY_HEADING_RE.match(nxt)
                        or BACK_HEADING_RE.match(nxt)
                        or ACK_HEADING_RE.match(nxt)
                        or HISTORY_LINE_RE.match(nxt)
                    ):
                        break
                    extras.append(nxt)
                    index += 1
                continue
            if HISTORY_LINE_RE.match(stripped):
                extras.append(stripped)
            index += 1
        selected = list(selected) + extras
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
        text, root = read_docx_document(tmp_path)
    except Exception as exc:
        raise FrontDocxError("Could not read DOCX file") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    front_text = extract_front_section(text)
    if not front_text.strip():
        raise FrontDocxError("No front section found in DOCX")
    return front_text, document_counts(text, root)
