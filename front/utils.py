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

CORRESPONDENCE_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"correspondence\s+to|"
    r"correspond[eê]ncia(?:\s+(?:para|a))?"
    r")\s*:?\s*(.*)$",
    re.IGNORECASE,
)
ASSOCIATE_EDITOR_INLINE_RE = re.compile(
    r"^associate\s+editor\s*:\s*\S",
    re.IGNORECASE,
)

EDITORIAL_BACK_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:"
    r"authors?'?\s+contributions?|"
    r"contribui[cç][aã]o\s+dos\s+autores|"
    r"conflicts?\s+of\s+interest|"
    r"conflitos?\s+de\s+interesses?|"
    r"ethics|associate\s+editor"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

REFERENCE_HEADING_RE = re.compile(
    r"^(?:\d+[.\)]\s*)?(?:references?|referências?|referencias?|"
    r"bibliography|bibliografia)\s*$",
    re.IGNORECASE,
)

HISTORY_LABELS = (
    "revision requested|revisions requested|"
    "revisão solicitada|revisões solicitadas|"
    "revisión solicitada|"
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
PUBLICATION_HISTORY_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    r"published(?:\s+online)?|"
    r"publicado(?:\s+online|\s+en\s+l[ií]nea)?|"
    r"publica[cç][aã]o(?:\s+online)?|"
    r"publicacion(?:\s+online)?"
    r")\b"
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
FRONT_MATTER_LABEL_RE = re.compile(
    r"^(?:abstract|resumo|resumen|"
    r"keywords|key\s*words|"
    r"palavras-chave|palavras\s+chave|"
    r"palabras-clave|palabras\s+clave|"
    r"descritores)\b",
    re.IGNORECASE,
)
FRONT_MATTER_LABEL_ONLY_RE = re.compile(
    r"^(?:abstract|resumo|resumen|"
    r"keywords|key\s*words|"
    r"palavras-chave|palavras\s+chave|"
    r"palabras-clave|palabras\s+clave|"
    r"descritores)\s*:?\s*$",
    re.IGNORECASE,
)
APA_REFERENCE_YEAR_RE = re.compile(r"\((?:1[6-9]|20)\d{2}[a-z]?\)\s*\.")
NUMBERED_REFERENCE_LINE_RE = re.compile(r"^\d{1,3}\s*[\.\)]\s+\S")
REFERENCE_YEAR_TOKEN_RE = re.compile(r"\b(?:1[6-9]|20)\d{2}[a-z]?\b")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
DOCX_NSMAP = {"w": W_NS, "m": M_NS}

FRONT_CHAR_LIMIT = 12000


def normalize_front_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def front_matter_end_index(lines):
    last = None
    for index, line in enumerate(lines):
        if FRONT_MATTER_LABEL_RE.match(str(line).strip()):
            last = index
    if last is None:
        return None
    if FRONT_MATTER_LABEL_ONLY_RE.match(str(lines[last]).strip()):
        for index in range(last + 1, len(lines)):
            if str(lines[index]).strip():
                return index
    return last


def reference_run_start_index(lines, search_from=0):
    run = 0
    run_start = None
    begin = max(0, int(search_from or 0))
    for index in range(begin, len(lines)):
        text = str(lines[index]).strip()
        if not text:
            continue
        numbered = bool(
            NUMBERED_REFERENCE_LINE_RE.match(text)
            and REFERENCE_YEAR_TOKEN_RE.search(text)
        )
        if APA_REFERENCE_YEAR_RE.search(text) or numbered:
            if run == 0:
                run_start = index
            run += 1
            if run >= 3:
                return run_start
            continue
        run = 0
        run_start = None
    return None


_CONTRIBUTION_LINE_RE = re.compile(
    r":\s*.*(?:study design|data analysis|field data|manuscript\s+revision|"
    r"manuscript\s+writing|initial draft|coleta de dados|an[aá]lise de dados|"
    r"reda[cç][aã]o do manuscrito)",
    re.IGNORECASE,
)
_CONFLICT_LINE_RE = re.compile(
    r"conflict of interest|conflito de interesses|no conflict of interest",
    re.IGNORECASE,
)
_ETHICS_LINE_RE = re.compile(
    r"did not involve human|n[aã]o envolveu seres humanos|"
    r"comit[eê] de [eé]tica|institutional committee|ethics committee",
    re.IGNORECASE,
)
_ACK_LINE_RE = re.compile(
    r"would like to (?:express|thank)|agradec(?:emos|imentos?|imento)|"
    r"financial support for the field|apoio financeiro",
    re.IGNORECASE,
)
_DATA_LINE_RE = re.compile(
    r"datasets generated|dados gerados|data availability|"
    r"disponibilidade de dados",
    re.IGNORECASE,
)
_PERSON_NAME_RE = re.compile(
    r"[A-ZÀ-Ý][\w.'’-]{1,30}(?:\s+[A-ZÀ-Ý][\w.'’-]{1,30}){1,3}"
)


def back_matter_lines(lines, boundary):
    if boundary is None:
        return [], []
    move = []
    copy = []
    seen_move = False
    steps = 0
    index = int(boundary) - 1
    while index >= 0 and steps < 40:
        text = str(lines[index]).strip()
        if not text:
            index -= 1
            continue
        steps += 1
        if _DATA_LINE_RE.search(text):
            kind = "keep"
        elif _ACK_LINE_RE.search(text):
            kind = "copy"
        elif (
            _CONTRIBUTION_LINE_RE.search(text)
            or _CONFLICT_LINE_RE.search(text)
            or _ETHICS_LINE_RE.search(text)
        ):
            kind = "move"
        elif _PERSON_NAME_RE.fullmatch(text):
            kind = "name"
        else:
            kind = "stop"
        if kind == "move":
            move.append(index)
            seen_move = True
        elif kind == "copy":
            copy.append(index)
        elif kind == "name" and seen_move:
            move.append(index)
        elif kind == "keep":
            pass
        else:
            break
        index -= 1
    move.reverse()
    copy.reverse()
    return move, copy


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
            break
    if start is None:
        start = reference_run_start_index(lines)
    n_refs = 0
    if start is not None:
        block = []
        for line in lines[start:]:
            if (
                COUNTS_STOP_RE.match(line)
                or FIGURE_CAPTION_RE.match(line)
                or TABLE_CAPTION_RE.match(line)
                or HISTORY_LINE_RE.match(line)
                or PUBLICATION_HISTORY_RE.match(line)
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
    matter_end = None if cut is not None else front_matter_end_index(lines)
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
            if EDITORIAL_BACK_HEADING_RE.match(stripped):
                extras.append(stripped)
                index += 1
                while index < len(lines):
                    nxt = lines[index].strip()
                    if not nxt:
                        index += 1
                        continue
                    if (
                        EDITORIAL_BACK_HEADING_RE.match(nxt)
                        or REFERENCE_HEADING_RE.match(nxt)
                        or ACK_HEADING_RE.match(nxt)
                        or BACK_HEADING_RE.match(nxt)
                        or HISTORY_LINE_RE.match(nxt)
                        or PUBLICATION_HISTORY_RE.match(nxt)
                        or BODY_HEADING_RE.match(nxt)
                    ):
                        break
                    extras.append(nxt)
                    index += 1
                continue
            if CORRESPONDENCE_HEADING_RE.match(stripped):
                extras.append(stripped)
                index += 1
                while index < len(lines):
                    nxt = lines[index].strip()
                    if not nxt:
                        index += 1
                        continue
                    if (
                        CORRESPONDENCE_HEADING_RE.match(nxt)
                        or EDITORIAL_BACK_HEADING_RE.match(nxt)
                        or REFERENCE_HEADING_RE.match(nxt)
                        or ACK_HEADING_RE.match(nxt)
                        or HISTORY_LINE_RE.match(nxt)
                        or PUBLICATION_HISTORY_RE.match(nxt)
                        or BODY_HEADING_RE.match(nxt)
                        or BACK_HEADING_RE.match(nxt)
                    ):
                        break
                    extras.append(nxt)
                    index += 1
                continue
            if (
                HISTORY_LINE_RE.match(stripped)
                or PUBLICATION_HISTORY_RE.match(stripped)
                or ASSOCIATE_EDITOR_INLINE_RE.match(stripped)
            ):
                extras.append(stripped)
            index += 1
        selected = list(selected) + extras
    elif matter_end is not None:
        selected = lines[: matter_end + 1]
        ref_start = reference_run_start_index(lines, matter_end + 1)
        move_idx, copy_idx = back_matter_lines(lines, ref_start)
        for index in sorted(set(move_idx) | set(copy_idx)):
            selected.append(lines[index])
        for line in lines[matter_end + 1 :]:
            stripped = line.strip()
            if HISTORY_LINE_RE.match(stripped) or PUBLICATION_HISTORY_RE.match(
                stripped
            ):
                selected.append(stripped)
    result = "\n".join(line.strip() for line in selected if line.strip())
    if cut is None and matter_end is None:
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
