import hashlib
import json
import logging
import re
import unicodedata

from django.db import IntegrityError
from lxml import etree

from front.exceptions import FrontLlamaUnavailableError
from front.marking import mark_front
from front.models import Front
from front.utils import HISTORY_LABEL_RE, PUBLICATION_HISTORY_RE, normalize_front_text

logger = logging.getLogger(__name__)

XLINK_NS = "http://www.w3.org/1999/xlink"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
CC_BY_HREF = "https://creativecommons.org/licenses/by/4.0/"
CC_BY_LICENSE_P = (
    "This is an Open Access article distributed under the terms of the "
    "Creative Commons Attribution License, which permits unrestricted use, "
    "distribution, and reproduction in any medium, provided the original "
    "work is properly cited."
)
CREDIT_URL = "https://credit.niso.org/contributor-roles/{}/"
CREDIT_ROLES = (
    (
        "writing-original-draft",
        "Writing – original draft",
        (
            "writing original draft",
            "writing the original draft",
            "original draft",
            "initial draft",
            "draft preparation",
            "wrote the manuscript",
            "wrote the paper",
            "redacao do manuscrito",
            "redacao original",
            "escrita do manuscrito",
        ),
    ),
    (
        "writing-review-editing",
        "Writing – review & editing",
        (
            "writing review editing",
            "writing review",
            "review and editing",
            "manuscript revision",
            "revision and approval",
            "revisao do manuscrito",
            "revisao e aprovacao",
            "approved the manuscript",
        ),
    ),
    (
        "formal-analysis",
        "Formal analysis",
        (
            "formal analysis",
            "data analysis",
            "statistical analysis",
            "analise formal",
            "analise de dados",
        ),
    ),
    (
        "investigation",
        "Investigation",
        (
            "investigation",
            "data collection",
            "field data",
            "field work",
            "fieldwork",
            "botanical identification",
            "coleta de dados",
            "trabalho de campo",
        ),
    ),
    (
        "methodology",
        "Methodology",
        ("methodology", "metodos", "metodologia"),
    ),
    (
        "conceptualization",
        "Conceptualization",
        (
            "conceptualization",
            "study design",
            "conception",
            "concepcao",
            "desenho do estudo",
        ),
    ),
    (
        "supervision",
        "Supervision",
        ("supervision", "leadership", "supervisao", "lideranca"),
    ),
    (
        "project-administration",
        "Project administration",
        ("project administration", "administracao do projeto"),
    ),
    (
        "funding-acquisition",
        "Funding acquisition",
        ("funding acquisition", "funding", "financiamento"),
    ),
    (
        "data-curation",
        "Data curation",
        ("data curation", "curadoria de dados"),
    ),
    (
        "resources",
        "Resources",
        ("resources", "recursos"),
    ),
    (
        "software",
        "Software",
        ("software",),
    ),
    (
        "validation",
        "Validation",
        ("validation", "validacao"),
    ),
    (
        "visualization",
        "Visualization",
        ("visualization", "visualizacao"),
    ),
)
HISTORY_DATE_TYPES = (
    "received",
    "rev-request",
    "rev-recd",
    "accepted",
    "pub",
)

COUNTRY_CODES = {
    "brasil": "BR",
    "brazil": "BR",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "mexico": "MX",
    "méxico": "MX",
    "peru": "PE",
    "perú": "PE",
    "portugal": "PT",
    "spain": "ES",
    "españa": "ES",
    "espanha": "ES",
    "united states": "US",
    "usa": "US",
    "estados unidos": "US",
    "france": "FR",
    "frança": "FR",
    "francia": "FR",
    "germany": "DE",
    "alemanha": "DE",
    "alemania": "DE",
    "united kingdom": "GB",
    "uk": "GB",
    "reino unido": "GB",
    "italy": "IT",
    "itália": "IT",
    "italia": "IT",
    "canada": "CA",
    "canadá": "CA",
    "uruguay": "UY",
    "uruguai": "UY",
    "paraguay": "PY",
    "paraguai": "PY",
    "bolivia": "BO",
    "bolívia": "BO",
    "ecuador": "EC",
    "equador": "EC",
    "venezuela": "VE",
    "cuba": "CU",
    "costa rica": "CR",
}

MONTH_NAMES = {
    "january": 1,
    "jan": 1,
    "janeiro": 1,
    "enero": 1,
    "ene": 1,
    "janvier": 1,
    "janv": 1,
    "february": 2,
    "feb": 2,
    "fevereiro": 2,
    "fev": 2,
    "febrero": 2,
    "fevrier": 2,
    "fevr": 2,
    "march": 3,
    "mar": 3,
    "marco": 3,
    "marzo": 3,
    "mars": 3,
    "april": 4,
    "apr": 4,
    "abril": 4,
    "abr": 4,
    "avril": 4,
    "avr": 4,
    "may": 5,
    "maio": 5,
    "mai": 5,
    "mayo": 5,
    "june": 6,
    "jun": 6,
    "junho": 6,
    "junio": 6,
    "juin": 6,
    "july": 7,
    "jul": 7,
    "julho": 7,
    "julio": 7,
    "juillet": 7,
    "juil": 7,
    "august": 8,
    "aug": 8,
    "agosto": 8,
    "ago": 8,
    "aout": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "setembro": 9,
    "set": 9,
    "septiembre": 9,
    "setiembre": 9,
    "septembre": 9,
    "october": 10,
    "oct": 10,
    "outubro": 10,
    "out": 10,
    "octubre": 10,
    "octobre": 10,
    "november": 11,
    "nov": 11,
    "novembro": 11,
    "noviembre": 11,
    "novembre": 11,
    "december": 12,
    "dec": 12,
    "dezembro": 12,
    "dez": 12,
    "diciembre": 12,
    "dic": 12,
    "decembre": 12,
}

HISTORY_TYPE_MAP = {
    "received": "received",
    "recebido": "received",
    "recibido": "received",
    "submitted": "received",
    "accepted": "accepted",
    "aceito": "accepted",
    "aceptado": "accepted",
    "aprovado": "accepted",
    "approved": "accepted",
    "revision requested": "rev-request",
    "revisions requested": "rev-request",
    "revisão solicitada": "rev-request",
    "revisões solicitadas": "rev-request",
    "revisión solicitada": "rev-request",
    "revised": "rev-recd",
    "revisado": "rev-recd",
}

_MONTH_ALT = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
_YMD_RE = re.compile(r"^(\d{4})\s+(\d{1,2})\s+(\d{1,2})")
_DMY_RE = re.compile(r"^(\d{1,2})\s+(\d{1,2})\s+(\d{4})")
_DMY_NAME_RE = re.compile(
    rf"^(?:the\s+)?(\d{{1,2}})\s+(?:(?:de|of)\s+)?({_MONTH_ALT})"
    rf"\s+(?:(?:de|of)\s+)?(\d{{4}})"
)
_MDY_NAME_RE = re.compile(rf"^({_MONTH_ALT})\s+(\d{{1,2}})\s+(\d{{4}})")

ISSN_OR_URL_RE = re.compile(r"^(ISSN\b|https?://|www\.)", re.IGNORECASE)
SKIP_MASTHEAD_LINE_RE = re.compile(
    r"^(?:https?://|www\.|doi\b|issn\b|articles?|artigos?|research|"
    r"original\s+article|short\s+communication|editorial|"
    r"letter\s+to\s+the\s+editor)\s*$",
    re.IGNORECASE,
)
JOURNAL_TRAILER_RE = re.compile(
    r"(?:"
    r"\s+\d+\s*\(\s*(?:\d+|suppl\.?\s*\d+)\s*\)\s*:.*"
    r"|,\s*vol(?:ume|\.)?\s*\d+.*"
    r"|\s+vol(?:ume|\.)?\s*\d+.*"
    r"|\s*·\s*\d{4}.*"
    r"|\.\s+\d{4}\s*[;,].*"
    r"|,\s+\d{4}\s*[;,].*"
    r"|\s+\d{4}\s*[;,].*"
    r")$",
    re.IGNORECASE,
)
KEYWORD_LINE_RE = re.compile(
    r"^(?P<label>palavras-chave|palabras\s*clave|key\s*words?|keywords?)"
    r"\s*:?\s*(?P<body>.*)$",
    re.IGNORECASE,
)
ISSN_VALUE_RE = re.compile(r"\bISSN\s*(\d{4}-\d{3}[\dXx])", re.IGNORECASE)
SCIELO_DOI_ISSN_RE = re.compile(r"10\.1590/(\d{4}-\d{4})-", re.IGNORECASE)
ABSTRACT_START_RE = re.compile(
    r"^(abstract|resumo|resumen)\s*:?\s*(.*)$",
    re.IGNORECASE,
)
ABSTRACT_STOP_RE = re.compile(
    r"^(?:acknowledg(?:e?ments?)?|agradecimentos?|received|accepted|"
    r"recebido|aceito|recibido|aceptado|submitted|aprovado|approved|"
    r"revised|revisado)\b",
    re.IGNORECASE,
)
AFF_LINE_RE = re.compile(r"^(\d{1,2})(?!\d)\s*(.+)$")
AFF_HINT_RE = re.compile(
    r"universid|institut|faculd|hospital|centro|college|school|"
    r",\s*(brasil|brazil|argentina|chile|portugal|mexico|españa|espanha)\s*\.?$",
    re.IGNORECASE,
)
STREET_RE = re.compile(
    r"^(av\.?|avenida|rua|r\.|rod\.?|rodovia|alameda|travessa|km)\b",
    re.IGNORECASE,
)
POSTAL_RE = re.compile(r"^(\d{5}-?\d{3})\s*(.*)$")
ORGDIV_RE = re.compile(
    r"^(laborat|institut|campus|grupo|museu|centro|faculdade|departamento|"
    r"dept\.?|herbário|herbario|escola|n[uú]cleo)\b",
    re.IGNORECASE,
)
ORCID_RE = re.compile(
    r"(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])",
    re.IGNORECASE,
)
FUNDING_HEADING_RE = re.compile(
    r"^(?:funding|financiamento|financial support)\:?\s*$",
    re.IGNORECASE,
)
FUNDING_STOP_RE = re.compile(
    r"^(?:competing interests|conflicts? of interest|conflict of interest|"
    r"acknowledg(?:e?ments?)?|agradecimentos?|authors?'?\s+contributions|"
    r"ethics|associate editor|references|refer[eê]ncias)\:?\s*$",
    re.IGNORECASE,
)
FUNDING_INLINE_RE = re.compile(
    r"^(?:this study was supported|financed by|supported by|"
    r"este trabalho foi apoiado|financiado por)\b",
    re.IGNORECASE,
)
SIMPLE_FUNDING_AWARD_RE = re.compile(
    r"\b(FAPESP|CNPq|CAPES|FAPEAM)\s+([\d][\d./-]*)",
    re.IGNORECASE,
)
FUNDING_AWARD_ID_RE = re.compile(
    r"(?:process(?:o|\s+no\.?)?|calls?\s+no\.?|no\.?|grant\s+no\.?)"
    r"\s*([\d]{2,4}/[\d]{4}(?:/[\d]+)?|[\d]{3,}-[\d]{4}-[\d]+|[\d]{3,}/[\d]{4}-[\d]+)",
    re.IGNORECASE,
)
AUTHOR_CONTRIB_HEADING_RE = re.compile(
    r"^(?:authors?'?\s+contributions?|contribui[cç][aã]o\s+dos\s+autores)\s*:?\s*$",
    re.IGNORECASE,
)
ASSOCIATE_EDITOR_HEADING_RE = re.compile(r"^associate\s+editor\s*:?\s*$", re.IGNORECASE)
COI_HEADING_RE = re.compile(
    r"^(?:conflicts?\s+of\s+interest|conflitos?\s+de\s+interesses?)\s*:?\s*$",
    re.IGNORECASE,
)
ETHICS_HEADING_RE = re.compile(r"^ethics\s*:?\s*$", re.IGNORECASE)
EDITORIAL_SECTION_STOP_RE = re.compile(
    r"^(?:authors?'?\s+contributions?|contribui[cç][aã]o\s+dos\s+autores|"
    r"associate\s+editor|conflicts?\s+of\s+interest|conflitos?\s+de\s+interesses?|"
    r"ethics|references|refer[eê]ncias|bibliography|bibliografia|"
    r"acknowledg(?:e?ments?)?|agradecimentos?|funding|financiamento|"
    r"received|accepted|recebido|aceito)\b",
    re.IGNORECASE,
)
AUTHOR_ROLE_LINE_RE = re.compile(r"^([^:]{3,}):\s*(.+)$")
NAME_PARTICLES = frozenset({"de", "da", "do", "dos", "das", "del"})
DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


NULL_TOKENS = {"null", "none", "undefined", "nil", "n/a", "na"}


def _blank(value):
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in NULL_TOKENS


def _text_el(parent, tag, value, attrib=None):
    if _blank(value):
        return None
    element = etree.SubElement(parent, tag, attrib=attrib or {})
    element.text = str(value).strip()
    return element


def _normalize_orcid(value):
    if _blank(value):
        return ""
    match = ORCID_RE.search(str(value).strip())
    return match.group(1) if match else str(value).strip()


def _fold_name(value):
    text = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return re.sub(r"[^\w\s-]", " ", text)


def _normalize_doi(value):
    if _blank(value):
        return ""
    text = str(value).strip()
    lower = text.lower()
    for prefix in DOI_PREFIXES:
        if lower.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text.rstrip(".,;:)]}»\"'")


def _country_code(affiliation):
    code = str(affiliation.get("country_code") or "").strip().upper()
    if len(code) == 2:
        return code
    name = str(affiliation.get("country") or "").strip().lower()
    return COUNTRY_CODES.get(name, "")


def _fold_date(value):
    text = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    text = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_int_part(value, lo, hi):
    if _blank(value):
        return None
    text = str(value).strip().strip(".")
    if not re.fullmatch(r"\d{1,4}", text):
        return None
    number = int(text)
    if lo <= number <= hi:
        return number
    return None


def _month_number(value):
    number = _as_int_part(value, 1, 12)
    if number is not None:
        return number
    return MONTH_NAMES.get(_fold_date(value))


def _parse_date_text(value):
    folded = _fold_date(value)
    if not folded:
        return {}
    day_n = None
    month_n = None
    year_n = None
    match = _YMD_RE.match(folded)
    if match:
        year_n = int(match.group(1))
        month_n = int(match.group(2))
        day_n = int(match.group(3))
    if day_n is None:
        match = _DMY_NAME_RE.match(folded)
        if match:
            day_n = int(match.group(1))
            month_n = MONTH_NAMES.get(match.group(2))
            year_n = int(match.group(3))
    if day_n is None:
        match = _MDY_NAME_RE.match(folded)
        if match:
            month_n = MONTH_NAMES.get(match.group(1))
            day_n = int(match.group(2))
            year_n = int(match.group(3))
    if day_n is None:
        match = _DMY_RE.match(folded)
        if match:
            day_n = int(match.group(1))
            month_n = int(match.group(2))
            year_n = int(match.group(3))
    if day_n is None or month_n is None or year_n is None:
        match = re.match(r"^(\d{4})\s+(\d{1,2})$", folded)
        if match:
            month_n = int(match.group(2))
            year_n = int(match.group(1))
            if 1 <= month_n <= 12 and 1000 <= year_n <= 9999:
                return {"month": f"{month_n:02d}", "year": str(year_n)}
        match = re.match(r"^(\d{4})$", folded)
        if match and 1000 <= int(match.group(1)) <= 9999:
            return {"year": match.group(1)}
        return {}
    if month_n > 12 and 1 <= day_n <= 12:
        day_n, month_n = month_n, day_n
    if not (1 <= day_n <= 31 and 1 <= month_n <= 12 and 1000 <= year_n <= 9999):
        return {}
    return {"day": f"{day_n:02d}", "month": f"{month_n:02d}", "year": str(year_n)}


def _date_parts(item):
    if not isinstance(item, dict):
        return {}
    parts = {"season": item.get("season")}
    raw = item.get("date")
    if _blank(raw):
        raw = " ".join(
            str(item.get(key)).strip()
            for key in ("day", "month", "year")
            if not _blank(item.get(key))
        )
    parsed = _parse_date_text(raw) if not _blank(raw) else {}
    if parsed:
        parts.update(parsed)
        return parts
    if not _blank(item.get("year")):
        parts["year"] = str(item.get("year")).strip()
    month_n = _month_number(item.get("month"))
    if month_n:
        parts["month"] = f"{month_n:02d}"
    day_n = _as_int_part(item.get("day"), 1, 31)
    if day_n:
        parts["day"] = f"{day_n:02d}"
    return parts


def _append_date_parts(parent, item):
    parts = _date_parts(item)
    _text_el(parent, "season", parts.get("season"))
    _text_el(parent, "day", parts.get("day"))
    _text_el(parent, "month", parts.get("month"))
    _text_el(parent, "year", parts.get("year"))
    return bool(list(parent))


def _append_abstract(parent, tag, item, with_lang=False):
    if not isinstance(item, dict):
        return
    text = item.get("text")
    sections = item.get("sections") or []
    title = item.get("title")
    if _blank(text) and not sections and _blank(title):
        return
    attrib = {}
    if with_lang and not _blank(item.get("language")):
        attrib["{http://www.w3.org/XML/1998/namespace}lang"] = str(
            item["language"]
        ).strip()
    abstract_type = item.get("abstract_type")
    if abstract_type == "key-points":
        attrib["abstract-type"] = "key-points"
    node = etree.SubElement(parent, tag, attrib=attrib)
    _text_el(node, "title", title)
    if sections:
        for section in sections:
            if not isinstance(section, dict):
                continue
            if _blank(section.get("title")) and _blank(section.get("text")):
                continue
            sec = etree.SubElement(node, "sec")
            _text_el(sec, "title", section.get("title"))
            _text_el(sec, "p", section.get("text"))
    elif not _blank(text):
        _text_el(node, "p", text)


def parse_marked(choice):
    if isinstance(choice, dict):
        return choice
    if not isinstance(choice, str) or not choice.strip():
        return None
    text = choice.strip()
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```.*$", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"(\}\]\}){2,}$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    snippet = text[start : end + 1] if start >= 0 and end > start else text
    previous = None
    while previous != snippet:
        previous = snippet
        snippet = re.sub(r",+\s*([}\]])", r"\1", snippet)
        snippet = re.sub(r",+\s*$", "", snippet)
    for candidate in (text, snippet):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        try:
            parsed, _ = json.JSONDecoder().raw_decode(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def apply_language_fallback(data, language):
    if not isinstance(data, dict) or _blank(language):
        return data if isinstance(data, dict) else {}
    lang = str(language).strip()
    marked = dict(data)
    keywords = []
    for group in marked.get("keywords") or []:
        if not isinstance(group, dict):
            continue
        item = dict(group)
        if _blank(item.get("language")):
            item["language"] = lang
        keywords.append(item)
    if keywords:
        marked["keywords"] = keywords
    return marked


def apply_text_fields(data, front_text):
    marked = dict(data) if isinstance(data, dict) else {}
    lines = [
        line.strip() for line in str(front_text or "").splitlines() if line.strip()
    ]
    journal_title = None
    for index, line in enumerate(lines[:8]):
        if SKIP_MASTHEAD_LINE_RE.match(line):
            continue
        stripped = JOURNAL_TRAILER_RE.sub("", line).strip()
        if not stripped:
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if JOURNAL_TRAILER_RE.search(line) or ISSN_OR_URL_RE.match(next_line):
            journal_title = stripped.strip(" .,;")
            break
    if journal_title:
        journal = (
            dict(marked["journal"]) if isinstance(marked.get("journal"), dict) else {}
        )
        journal["journal_title"] = journal_title
        marked["journal"] = journal
    groups = []
    for line in lines:
        match = KEYWORD_LINE_RE.match(line)
        if not match:
            continue
        body = match.group("body").strip().strip(".")
        if not body:
            continue
        parts = body.split(";") if ";" in body else body.split(",")
        words = [part.strip().strip(".") for part in parts if part.strip().strip(".")]
        if not words:
            continue
        label = re.sub(r"\s+", " ", match.group("label")).strip()
        lower = label.lower()
        if lower.startswith("palavra"):
            language = "pt"
            title = "Palavras-chave"
        elif lower.startswith("palabra"):
            language = "es"
            title = "Palabras clave"
        else:
            language = "en"
            title = "Keywords"
        groups.append({"language": language, "title": title, "keywords": words})
    if groups:
        marked["keywords"] = groups
    authors = [
        dict(item) for item in (marked.get("authors") or []) if isinstance(item, dict)
    ]
    if authors:
        pairs = []
        for line in lines:
            matches = list(ORCID_RE.finditer(line))
            for index, match in enumerate(matches):
                start = 0 if index == 0 else matches[index - 1].end()
                pairs.append((_fold_name(line[start : match.start()]), match.group(1)))
        used = set()
        filled = []
        for author in authors:
            current = _normalize_orcid(author.get("orcid"))
            if current:
                author["orcid"] = current
                used.add(current)
                filled.append(author)
                continue
            surname = _fold_name(author.get("surname")).strip()
            given = _fold_name(author.get("given_names"))
            best = None
            best_score = 0
            if surname:
                surname_re = re.compile(r"(?<!\w)" + re.escape(surname) + r"(?!\w)")
                given_tokens = [
                    tok
                    for tok in re.findall(r"[a-z]+", given)
                    if tok not in {"de", "da", "do", "dos", "das", "del"}
                ]
                for folded, orcid in pairs:
                    if orcid in used or not surname_re.search(folded):
                        continue
                    score = 1 + sum(
                        1
                        for tok in given_tokens
                        if re.search(r"(?<!\w)" + re.escape(tok) + r"(?!\w)", folded)
                    )
                    if score > best_score:
                        best_score = score
                        best = orcid
            if best:
                author["orcid"] = best
                used.add(best)
            filled.append(author)
        marked["authors"] = filled
    source_issns = []
    seen_issn = set()
    for line in lines:
        match = ISSN_VALUE_RE.search(line)
        if not match:
            continue
        issn_value = match.group(1).upper()
        if issn_value in seen_issn:
            continue
        seen_issn.add(issn_value)
        folded = line.lower()
        if re.search(r"print|impresso|printed|ppub", folded):
            pub_type = "ppub"
        elif re.search(r"online|eletr[oô]nico|on-line|epub", folded):
            pub_type = "epub"
        else:
            pub_type = "epub"
        source_issns.append({"pub_type": pub_type, "value": issn_value})
    if not source_issns:
        match = SCIELO_DOI_ISSN_RE.search(" ".join(lines))
        if match:
            source_issns.append({"pub_type": "epub", "value": match.group(1)})
    journal = dict(marked["journal"]) if isinstance(marked.get("journal"), dict) else {}
    if source_issns:
        journal["issns"] = source_issns
        marked["journal"] = journal
    elif "issns" in journal:
        journal.pop("issns")
        if journal:
            marked["journal"] = journal
        else:
            marked.pop("journal", None)
    abstracts = []
    index = 0
    while index < len(lines):
        match = ABSTRACT_START_RE.match(lines[index])
        if not match:
            index += 1
            continue
        label = match.group(1).strip().lower()
        chunks = []
        body = match.group(2).strip()
        if body:
            chunks.append(body)
        index += 1
        while index < len(lines):
            nxt = lines[index]
            if (
                ABSTRACT_START_RE.match(nxt)
                or KEYWORD_LINE_RE.match(nxt)
                or ABSTRACT_STOP_RE.match(nxt)
            ):
                break
            chunks.append(nxt)
            index += 1
        text = " ".join(chunks).strip()
        if not text:
            continue
        if label == "abstract":
            abstracts.append({"kind": "main", "title": "Abstract", "text": text})
        elif label == "resumo":
            abstracts.append(
                {
                    "kind": "translated",
                    "language": "pt",
                    "title": "Resumo",
                    "text": text,
                }
            )
        else:
            abstracts.append(
                {
                    "kind": "translated",
                    "language": "es",
                    "title": "Resumen",
                    "text": text,
                }
            )
    if abstracts:
        marked["abstracts"] = abstracts
    affiliations = []
    for line in lines:
        match = AFF_LINE_RE.match(line)
        if not match or "orcid" in line.lower():
            continue
        original = match.group(2).strip().rstrip(".")
        if not AFF_HINT_RE.search(original):
            continue
        label = match.group(1)
        parts = [part.strip() for part in original.split(",") if part.strip()]
        if not parts:
            continue
        orgname = parts[0]
        rest = parts[1:]
        country = None
        state = None
        city = None
        postal_code = None
        if rest:
            tail = rest[-1].rstrip(".").lower()
            if tail in COUNTRY_CODES:
                country = rest.pop().rstrip(".")
        if rest and re.fullmatch(r"[A-Z]{2}", rest[-1].rstrip(".")):
            state = rest.pop().rstrip(".")
        while rest:
            part = rest[-1]
            postal_match = POSTAL_RE.match(part)
            if postal_match:
                postal_code = postal_match.group(1)
                leftover = postal_match.group(2).strip().rstrip(".")
                if leftover and not city:
                    city = leftover
                rest.pop()
                continue
            if STREET_RE.match(part) or re.fullmatch(r"\d+", part):
                rest.pop()
                continue
            if not city and not ORGDIV_RE.match(part):
                city = part.rstrip(".")
                rest.pop()
                continue
            break
        orgdivs = [
            part.rstrip(".")
            for part in rest
            if not STREET_RE.match(part) and not re.fullmatch(r"\d+", part)
        ]
        item = {
            "id": f"aff{label}",
            "label": label,
            "original": original,
            "orgname": orgname,
        }
        if orgdivs:
            item["orgdiv1"] = orgdivs[0]
        if len(orgdivs) > 1:
            item["orgdiv2"] = orgdivs[1]
        if city:
            item["city"] = city
        if state:
            item["state"] = state
        if postal_code:
            item["postal_code"] = postal_code
        if country:
            item["country"] = country
            item["country_code"] = COUNTRY_CODES.get(country.lower(), "")
        affiliations.append(item)
    if affiliations:
        marked["affiliations"] = affiliations
    history = []
    seen = set()
    history_text = "\n".join(lines)
    for match in HISTORY_LABEL_RE.finditer(history_text):
        date_type = HISTORY_TYPE_MAP.get(match.group("label").lower())
        if not date_type or date_type in seen:
            continue
        parsed = _parse_date_text(history_text[match.end() : match.end() + 80])
        if _blank(parsed.get("year")):
            continue
        history.append({"type": date_type, **parsed})
        seen.add(date_type)
    for match in PUBLICATION_HISTORY_RE.finditer(history_text):
        if "pub" in seen:
            continue
        parsed = _parse_date_text(history_text[match.end() : match.end() + 80])
        if (
            _blank(parsed.get("year"))
            or _blank(parsed.get("month"))
            or _blank(parsed.get("day"))
        ):
            continue
        history.append({"type": "pub", **parsed})
        seen.add("pub")
    if history:
        marked["history"] = history
        for item in history:
            if str(item.get("type")).strip() != "pub":
                continue
            if (
                _blank(item.get("day"))
                or _blank(item.get("month"))
                or _blank(item.get("year"))
            ):
                continue
            pub_dates = [
                entry
                for entry in (marked.get("pub_dates") or [])
                if isinstance(entry, dict)
            ]
            have_pub = any(
                str(entry.get("type")).strip() == "pub" for entry in pub_dates
            )
            if not have_pub:
                pub_dates.append(
                    {
                        "type": "pub",
                        "day": item["day"],
                        "month": item["month"],
                        "year": item["year"],
                    }
                )
                marked["pub_dates"] = pub_dates
            break
    funding_lines = []
    capture_funding = False
    for line in lines:
        if FUNDING_HEADING_RE.match(line):
            capture_funding = True
            continue
        if capture_funding:
            if FUNDING_STOP_RE.match(line):
                break
            funding_lines.append(line)
            continue
        if FUNDING_INLINE_RE.match(line):
            funding_lines.append(line)
    if not funding_lines:
        for line in lines:
            if SIMPLE_FUNDING_AWARD_RE.search(line) and not KEYWORD_LINE_RE.match(line):
                funding_lines.append(line)
    funding_statement = " ".join(funding_lines).strip()
    if funding_statement:
        awards = []
        seen_awards = set()
        for agency, award_id in SIMPLE_FUNDING_AWARD_RE.findall(funding_statement):
            source = "CNPq" if agency.upper() == "CNPQ" else agency.upper()
            key = (source, award_id.strip())
            if key in seen_awards:
                continue
            seen_awards.add(key)
            awards.append({"funding_source": source, "award_id": award_id.strip()})
        if re.search(r"\bFAPEAM\b", funding_statement, re.IGNORECASE):
            fapeam_part = funding_statement
            if re.search(r"\bCAPES\b", funding_statement, re.IGNORECASE):
                fapeam_part = re.split(
                    r"\bCAPES\b", funding_statement, maxsplit=1, flags=re.IGNORECASE
                )[0]
            for award_id in FUNDING_AWARD_ID_RE.findall(fapeam_part):
                key = ("FAPEAM", award_id)
                if key in seen_awards:
                    continue
                seen_awards.add(key)
                awards.append({"funding_source": "FAPEAM", "award_id": award_id})
        if re.search(r"\bCAPES\b", funding_statement, re.IGNORECASE):
            capes_part = re.split(
                r"\bCAPES\b", funding_statement, maxsplit=1, flags=re.IGNORECASE
            )[-1]
            for award_id in FUNDING_AWARD_ID_RE.findall(capes_part):
                key = ("CAPES", award_id)
                if key in seen_awards:
                    continue
                seen_awards.add(key)
                awards.append({"funding_source": "CAPES", "award_id": award_id})
        marked["funding"] = {
            "awards": awards,
            "funding_statement": funding_statement,
        }
    contrib_role_lines = []
    capture_contrib = False
    associate_editor_name = None
    capture_editor = False
    coi_lines = []
    capture_coi = False
    ethics_lines = []
    capture_ethics = False
    for line in lines:
        if AUTHOR_CONTRIB_HEADING_RE.match(line):
            capture_contrib = True
            capture_editor = False
            capture_coi = False
            capture_ethics = False
            continue
        if ASSOCIATE_EDITOR_HEADING_RE.match(line):
            capture_editor = True
            capture_contrib = False
            capture_coi = False
            capture_ethics = False
            continue
        if COI_HEADING_RE.match(line):
            capture_coi = True
            capture_contrib = False
            capture_editor = False
            capture_ethics = False
            continue
        if ETHICS_HEADING_RE.match(line):
            capture_ethics = True
            capture_contrib = False
            capture_editor = False
            capture_coi = False
            continue
        if capture_contrib:
            if EDITORIAL_SECTION_STOP_RE.match(line):
                capture_contrib = False
                continue
            role_match = AUTHOR_ROLE_LINE_RE.match(line)
            if role_match:
                contrib_role_lines.append(
                    (role_match.group(1).strip(), role_match.group(2).strip())
                )
            continue
        if capture_editor:
            if EDITORIAL_SECTION_STOP_RE.match(line):
                capture_editor = False
                continue
            associate_editor_name = line
            capture_editor = False
            continue
        if capture_coi:
            if EDITORIAL_SECTION_STOP_RE.match(line):
                capture_coi = False
                continue
            coi_lines.append(line)
            continue
        if capture_ethics:
            if EDITORIAL_SECTION_STOP_RE.match(line):
                capture_ethics = False
                continue
            ethics_lines.append(line)
    if contrib_role_lines:
        authors_for_roles = [
            dict(item)
            for item in (marked.get("authors") or [])
            if isinstance(item, dict)
        ]
        if authors_for_roles:
            updated_authors = []
            for author in authors_for_roles:
                item = dict(author)
                surname = _fold_name(item.get("surname")).strip()
                given = _fold_name(item.get("given_names"))
                given_tokens = [
                    token
                    for token in re.findall(r"[a-z]+", given)
                    if token not in NAME_PARTICLES
                ]
                best_roles = None
                best_score = 0
                for name_part, roles_text in contrib_role_lines:
                    folded = _fold_name(name_part)
                    if not surname or not re.search(
                        r"(?<!\w)" + re.escape(surname) + r"(?!\w)", folded
                    ):
                        continue
                    score = 2
                    for token in given_tokens:
                        if len(token) == 1:
                            if re.search(
                                r"(?<!\w)" + re.escape(token) + r"(?!\w)", folded
                            ):
                                score += 1
                        elif re.search(
                            r"(?<!\w)" + re.escape(token) + r"(?!\w)", folded
                        ):
                            score += 2
                        elif token[:1] and re.search(
                            r"(?<!\w)" + re.escape(token[:1]) + r"(?!\w)", folded
                        ):
                            score += 1
                    if score > best_score:
                        best_score = score
                        best_roles = [
                            part.strip().rstrip(".")
                            for part in re.split(r"\s*;\s*", roles_text)
                            if part.strip()
                        ]
                if best_roles:
                    item["roles"] = best_roles
                updated_authors.append(item)
            marked["authors"] = updated_authors
    editorial_fns = []
    if associate_editor_name:
        editorial_fns.append(
            {
                "fn_type": "edited-by",
                "label": "Associate Editor",
                "text": associate_editor_name,
            }
        )
    coi_text = " ".join(coi_lines).strip()
    if coi_text:
        editorial_fns.append(
            {
                "fn_type": "coi-statement",
                "label": "Conflicts of Interest",
                "text": coi_text,
            }
        )
    ethics_text = " ".join(ethics_lines).strip()
    if ethics_text:
        editorial_fns.append(
            {
                "fn_type": "other",
                "label": "Ethics",
                "text": ethics_text,
            }
        )
    if editorial_fns:
        notes = (
            dict(marked["author_notes"])
            if isinstance(marked.get("author_notes"), dict)
            else {}
        )
        replace_types = {fn["fn_type"] for fn in editorial_fns}
        existing = [
            item
            for item in (notes.get("fns") or [])
            if not (isinstance(item, dict) and item.get("fn_type") in replace_types)
        ]
        notes["fns"] = existing + editorial_fns
        marked["author_notes"] = notes
    return marked


def get_front_xml(data):
    if not isinstance(data, dict):
        data = {}

    front = etree.Element("front", nsmap={"xlink": XLINK_NS})
    journal = data.get("journal") if isinstance(data.get("journal"), dict) else {}

    journal_ids = journal.get("journal_ids") or []
    issns = journal.get("issns") or []
    has_journal = any(
        [
            journal_ids,
            not _blank(journal.get("journal_title")),
            not _blank(journal.get("abbrev_journal_title")),
            issns,
            not _blank(journal.get("publisher_name")),
        ]
    )
    if has_journal:
        journal_meta = etree.SubElement(front, "journal-meta")
        for item in journal_ids:
            if not isinstance(item, dict):
                continue
            jtype = str(item.get("type") or "").strip()
            if jtype not in ("publisher-id", "nlm-ta"):
                continue
            _text_el(
                journal_meta,
                "journal-id",
                item.get("value"),
                attrib={"journal-id-type": jtype},
            )
        if not _blank(journal.get("journal_title")) or not _blank(
            journal.get("abbrev_journal_title")
        ):
            title_group = etree.SubElement(journal_meta, "journal-title-group")
            _text_el(title_group, "journal-title", journal.get("journal_title"))
            _text_el(
                title_group,
                "abbrev-journal-title",
                journal.get("abbrev_journal_title"),
            )
        for item in issns:
            if not isinstance(item, dict):
                continue
            pub_type = str(item.get("pub_type") or "").strip()
            attrib = {}
            if pub_type in ("epub", "ppub"):
                attrib["pub-type"] = pub_type
            _text_el(journal_meta, "issn", item.get("value"), attrib=attrib)
        if not _blank(journal.get("publisher_name")):
            publisher = etree.SubElement(journal_meta, "publisher")
            _text_el(publisher, "publisher-name", journal.get("publisher_name"))

    article_meta = etree.SubElement(front, "article-meta")

    for item in data.get("article_ids") or []:
        if not isinstance(item, dict):
            continue
        pub_id_type = str(item.get("pub_id_type") or "").strip()
        if pub_id_type not in ("doi", "publisher-id", "other"):
            continue
        value = item.get("value")
        if pub_id_type == "doi":
            value = _normalize_doi(value)
        _text_el(
            article_meta,
            "article-id",
            value,
            attrib={"pub-id-type": pub_id_type},
        )

    categories = [
        item
        for item in (data.get("categories") or [])
        if isinstance(item, dict) and not _blank(item.get("subject"))
    ]
    if categories:
        article_categories = etree.SubElement(article_meta, "article-categories")
        for item in categories:
            group_type = str(item.get("subj_group_type") or "").strip() or "heading"
            group = etree.SubElement(
                article_categories,
                "subj-group",
                attrib={"subj-group-type": group_type},
            )
            _text_el(group, "subject", item.get("subject"))

    titles = [item for item in (data.get("titles") or []) if isinstance(item, dict)]
    main_titles = [
        item
        for item in titles
        if item.get("kind") == "main" and not _blank(item.get("text"))
    ]
    trans_titles = [
        item
        for item in titles
        if item.get("kind") == "translated"
        and not _blank(item.get("text"))
        and not _blank(item.get("language"))
    ]
    if not main_titles:
        main_titles = [
            item
            for item in titles
            if item.get("kind") not in ("translated",) and not _blank(item.get("text"))
        ]
    if main_titles or trans_titles:
        title_group = etree.SubElement(article_meta, "title-group")
        if main_titles:
            _text_el(title_group, "article-title", main_titles[0].get("text"))
        for item in trans_titles:
            group = etree.SubElement(
                title_group,
                "trans-title-group",
                attrib={
                    "{http://www.w3.org/XML/1998/namespace}lang": str(
                        item["language"]
                    ).strip()
                },
            )
            _text_el(group, "trans-title", item.get("text"))

    affiliations = [
        item
        for item in (data.get("affiliations") or [])
        if isinstance(item, dict) and not _blank(item.get("id"))
    ]
    aff_by_id = {}
    aff_by_label = {}
    for affiliation in affiliations:
        aff_id = str(affiliation.get("id")).strip()
        aff_by_id[aff_id] = affiliation
        label = str(affiliation.get("label") or "").strip()
        if label:
            aff_by_label[label] = affiliation
    default_aff_id = next(iter(aff_by_id), None)

    authors = [item for item in (data.get("authors") or []) if isinstance(item, dict)]
    if authors:
        contrib_group = etree.SubElement(article_meta, "contrib-group")
        for author in authors:
            contrib_type = str(author.get("contrib_type") or "author").strip()
            allowed = (
                "author",
                "compiler",
                "editor",
                "illustrator",
                "translator",
                "research-assistant",
                "reviewer",
            )
            if contrib_type not in allowed:
                contrib_type = "author"
            contrib = etree.SubElement(
                contrib_group, "contrib", attrib={"contrib-type": contrib_type}
            )
            orcid = _normalize_orcid(author.get("orcid"))
            if orcid:
                _text_el(
                    contrib,
                    "contrib-id",
                    orcid,
                    attrib={"contrib-id-type": "orcid"},
                )
            if (
                not _blank(author.get("collab"))
                and _blank(author.get("surname"))
                and _blank(author.get("given_names"))
            ):
                _text_el(contrib, "collab", author.get("collab"))
            elif not _blank(author.get("surname")) or not _blank(
                author.get("given_names")
            ):
                name = etree.SubElement(contrib, "name")
                _text_el(name, "surname", author.get("surname"))
                _text_el(name, "given-names", author.get("given_names"))
            resolved_affs = []
            seen_affs = set()
            for aff_id in author.get("affiliations") or []:
                key = str(aff_id).strip()
                if _blank(key):
                    continue
                if key in aff_by_id:
                    resolved = key
                elif key in aff_by_label:
                    resolved = str(aff_by_label[key].get("id")).strip()
                elif f"aff{key}" in aff_by_id:
                    resolved = f"aff{key}"
                else:
                    resolved = key
                if resolved in seen_affs:
                    continue
                seen_affs.add(resolved)
                resolved_affs.append(resolved)
            if not resolved_affs and default_aff_id:
                resolved_affs = [default_aff_id]
            for aff_id in resolved_affs:
                xref = etree.SubElement(
                    contrib,
                    "xref",
                    attrib={"ref-type": "aff", "rid": aff_id},
                )
                affiliation = aff_by_id.get(aff_id)
                label = affiliation.get("label") if affiliation else None
                if not _blank(label):
                    _text_el(xref, "sup", label)
            if author.get("corresp"):
                etree.SubElement(
                    contrib, "xref", attrib={"ref-type": "corresp", "rid": "c01"}
                )
            role_texts = []
            for role in author.get("roles") or []:
                if _blank(role):
                    continue
                text = str(role).strip().rstrip(".")
                if ";" in text:
                    role_texts.extend(
                        part.strip().rstrip(".")
                        for part in text.split(";")
                        if part.strip()
                    )
                else:
                    role_texts.append(text)
            for role_text in role_texts:
                folded = _fold_name(role_text)
                matched = None
                for slug, term, aliases in CREDIT_ROLES:
                    if any(alias in folded for alias in aliases):
                        matched = (slug, term)
                        break
                if matched:
                    slug, term = matched
                    _text_el(
                        contrib,
                        "role",
                        term,
                        attrib={"content-type": CREDIT_URL.format(slug)},
                    )
                else:
                    _text_el(contrib, "role", role_text)

    for affiliation in data.get("affiliations") or []:
        if not isinstance(affiliation, dict):
            continue
        aff_id = str(affiliation.get("id") or "").strip()
        if not aff_id:
            continue
        aff = etree.SubElement(article_meta, "aff", attrib={"id": aff_id})
        _text_el(aff, "label", affiliation.get("label"))
        _text_el(
            aff,
            "institution",
            affiliation.get("original"),
            attrib={"content-type": "original"},
        )
        _text_el(
            aff,
            "institution",
            affiliation.get("orgname"),
            attrib={"content-type": "orgname"},
        )
        _text_el(
            aff,
            "institution",
            affiliation.get("orgdiv1"),
            attrib={"content-type": "orgdiv1"},
        )
        _text_el(
            aff,
            "institution",
            affiliation.get("orgdiv2"),
            attrib={"content-type": "orgdiv2"},
        )
        addr_fields = (
            affiliation.get("city"),
            affiliation.get("state"),
            affiliation.get("postal_code"),
        )
        if any(not _blank(field) for field in addr_fields):
            addr_line = etree.SubElement(aff, "addr-line")
            _text_el(addr_line, "city", affiliation.get("city"))
            _text_el(addr_line, "state", affiliation.get("state"))
            _text_el(addr_line, "postal-code", affiliation.get("postal_code"))
        country_name = affiliation.get("country")
        code = _country_code(affiliation)
        if not _blank(country_name) or code:
            attrib = {"country": code} if code else {}
            _text_el(aff, "country", country_name or code, attrib=attrib)
        _text_el(aff, "email", affiliation.get("email"))

    author_notes = data.get("author_notes")
    if isinstance(author_notes, dict):
        notes = etree.Element("author-notes")
        corresp = author_notes.get("corresp")
        if not _blank(corresp):
            _text_el(notes, "corresp", corresp, attrib={"id": "c01"})
        for fn_item in author_notes.get("fns") or []:
            if isinstance(fn_item, dict):
                fn_type = str(fn_item.get("fn_type") or "").strip()
                label = fn_item.get("label")
                text = fn_item.get("text")
                fn_id = fn_item.get("id")
                attrib = {}
                if fn_type:
                    attrib["fn-type"] = fn_type
                if not _blank(fn_id):
                    attrib["id"] = str(fn_id).strip()
                if not attrib and _blank(label) and _blank(text):
                    continue
                fn = etree.SubElement(notes, "fn", attrib=attrib)
                _text_el(fn, "label", label)
                _text_el(fn, "p", text)
            elif not _blank(fn_item):
                _text_el(notes, "fn", fn_item)
        if list(notes):
            article_meta.append(notes)

    pub_dates = [
        item
        for item in (data.get("pub_dates") or [])
        if isinstance(item, dict)
        and str(item.get("type") or "").strip() in ("pub", "collection")
    ]
    have_collection = any(
        str(item.get("type")).strip() == "collection" for item in pub_dates
    )
    pub_year = None
    for item in pub_dates:
        parts = _date_parts(item)
        if not _blank(parts.get("year")):
            pub_year = parts["year"]
            break
    if not pub_year:
        history_source = data.get("history") or data.get("dates") or []
        preferred = []
        others = []
        for item in history_source:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() == "accepted":
                preferred.append(item)
            else:
                others.append(item)
        for item in preferred + others:
            parts = _date_parts(item)
            if not _blank(parts.get("year")):
                pub_year = parts["year"]
                break
    if not pub_year:
        permissions = data.get("permissions")
        if isinstance(permissions, dict) and not _blank(
            permissions.get("copyright_year")
        ):
            pub_year = str(permissions.get("copyright_year")).strip()
    if pub_year and not have_collection:
        pub_dates.append({"type": "collection", "year": pub_year})
    for item in pub_dates:
        date_type = str(item.get("type") or "").strip()
        pub_date = etree.SubElement(
            article_meta,
            "pub-date",
            attrib={
                "date-type": date_type,
                "publication-format": "electronic",
            },
        )
        parts = _date_parts(item)
        if date_type == "pub":
            year = parts.get("year")
            month = parts.get("month")
            day = parts.get("day")
            if _blank(year) or _blank(month) or _blank(day):
                article_meta.remove(pub_date)
                continue
            _text_el(pub_date, "day", day)
            _text_el(pub_date, "month", month)
            _text_el(pub_date, "year", year)
        elif not _append_date_parts(pub_date, item):
            article_meta.remove(pub_date)

    _text_el(article_meta, "volume", data.get("volume"))
    _text_el(article_meta, "issue", data.get("issue"))
    if not _blank(data.get("elocation_id")):
        _text_el(article_meta, "elocation-id", data.get("elocation_id"))
    else:
        _text_el(article_meta, "fpage", data.get("fpage"))
        _text_el(article_meta, "lpage", data.get("lpage"))

    history_items = [
        item
        for item in (data.get("history") or data.get("dates") or [])
        if isinstance(item, dict)
        and str(item.get("type") or "").strip() in HISTORY_DATE_TYPES
    ]
    if history_items:
        history = etree.SubElement(article_meta, "history")
        for item in history_items:
            date_el = etree.SubElement(
                history,
                "date",
                attrib={"date-type": str(item.get("type")).strip()},
            )
            if not _append_date_parts(date_el, item):
                history.remove(date_el)
        if not list(history):
            article_meta.remove(history)

    perm = etree.Element("permissions")
    permissions = data.get("permissions")
    if isinstance(permissions, dict):
        _text_el(perm, "copyright-statement", permissions.get("copyright_statement"))
        _text_el(perm, "copyright-year", permissions.get("copyright_year"))
        _text_el(perm, "copyright-holder", permissions.get("copyright_holder"))
    license_el = etree.SubElement(
        perm,
        "license",
        attrib={
            "license-type": "open-access",
            "{%s}href" % XLINK_NS: CC_BY_HREF,
            XML_LANG: "en",
        },
    )
    _text_el(license_el, "license-p", CC_BY_LICENSE_P)
    article_meta.append(perm)

    abstracts = [
        item for item in (data.get("abstracts") or []) if isinstance(item, dict)
    ]
    for item in abstracts:
        kind = item.get("kind")
        if kind == "translated":
            if _blank(item.get("language")):
                continue
            _append_abstract(article_meta, "trans-abstract", item, with_lang=True)
        else:
            _append_abstract(article_meta, "abstract", item, with_lang=False)

    for group in data.get("keywords") or []:
        if not isinstance(group, dict):
            continue
        words = []
        raw_words = group.get("keywords") or []
        if isinstance(raw_words, str):
            raw_words = [raw_words]
        for word in raw_words:
            if _blank(word):
                continue
            text = str(word).strip().rstrip(".")
            if ";" in text:
                for part in text.split(";"):
                    part = part.strip().strip(".")
                    if part:
                        words.append(part)
            else:
                words.append(text)
        if not words:
            continue
        attrib = {}
        if not _blank(group.get("language")):
            attrib["{http://www.w3.org/XML/1998/namespace}lang"] = str(
                group["language"]
            ).strip()
        kwd_group = etree.SubElement(article_meta, "kwd-group", attrib=attrib)
        _text_el(kwd_group, "title", group.get("title"))
        for word in words:
            _text_el(kwd_group, "kwd", word)

    funding = data.get("funding")
    if isinstance(funding, dict):
        funding_group = etree.Element("funding-group")
        for award in funding.get("awards") or []:
            if not isinstance(award, dict):
                continue
            if _blank(award.get("funding_source")) and _blank(award.get("award_id")):
                continue
            award_group = etree.SubElement(funding_group, "award-group")
            _text_el(award_group, "funding-source", award.get("funding_source"))
            _text_el(award_group, "award-id", award.get("award_id"))
        _text_el(funding_group, "funding-statement", funding.get("funding_statement"))
        if list(funding_group):
            article_meta.append(funding_group)

    counts = data.get("counts")
    if isinstance(counts, dict):
        counts_el = etree.Element("counts")
        for key, tag in (
            ("fig_count", "fig-count"),
            ("table_count", "table-count"),
            ("equation_count", "equation-count"),
            ("ref_count", "ref-count"),
        ):
            if _blank(counts.get(key)):
                continue
            etree.SubElement(
                counts_el, tag, attrib={"count": str(counts.get(key)).strip()}
            )
        if list(counts_el):
            article_meta.append(counts_el)

    return etree.tostring(front, pretty_print=True, encoding="unicode")


def resolve_front_result(
    front_text, user=None, output_type="json", language=None, counts=None
):
    normalized = normalize_front_text(front_text)
    checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    try:
        record = Front.objects.get(checksum=checksum)
    except Front.DoesNotExist:
        marked = None
        raw = ""
        for attempt in range(3):
            raw = mark_front(front_text)
            marked = parse_marked(raw)
            if marked is not None:
                break
            logger.warning(
                "Front Llama invalid JSON attempt %d/3 (%d chars): %r",
                attempt + 1,
                len(str(raw or "")),
                str(raw or "")[:500],
            )
        if marked is None:
            raise FrontLlamaUnavailableError("Front Llama returned invalid JSON")
        marked = apply_language_fallback(marked, language)
        marked = apply_text_fields(marked, front_text)
        xml = get_front_xml(marked)
        try:
            record, created = Front.objects.get_or_create(
                checksum=checksum,
                defaults={
                    "source_text": front_text,
                    "marked": marked,
                    "marked_xml": xml,
                    "creator": user,
                },
            )
        except IntegrityError:
            record = Front.objects.get(checksum=checksum)
            created = False
        if not created and not record.marked:
            record.marked = marked
            record.marked_xml = xml
            record.save(update_fields=["marked", "marked_xml", "updated"])

    marked = record.marked
    xml = record.marked_xml
    if isinstance(counts, dict) and any(not _blank(value) for value in counts.values()):
        marked = dict(marked or {})
        marked["counts"] = counts
        xml = get_front_xml(marked)
    if output_type == "xml":
        data = xml
    else:
        data = marked
    return {"data": data}
