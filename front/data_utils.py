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
from front.utils import HISTORY_LABEL_RE, normalize_front_text

logger = logging.getLogger(__name__)

XLINK_NS = "http://www.w3.org/1999/xlink"

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
    try:
        parsed = json.loads(choice)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    start = choice.find("{")
    end = choice.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(choice[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
    issn_value = None
    for line in lines:
        match = ISSN_VALUE_RE.search(line)
        if match:
            issn_value = match.group(1).upper()
            break
    if not issn_value:
        match = SCIELO_DOI_ISSN_RE.search(" ".join(lines))
        if match:
            issn_value = match.group(1)
    if issn_value:
        journal = (
            dict(marked["journal"]) if isinstance(marked.get("journal"), dict) else {}
        )
        issns = [
            dict(item)
            for item in (journal.get("issns") or [])
            if isinstance(item, dict)
        ]
        existing = {
            str(item.get("value") or "").strip()
            for item in issns
            if not _blank(item.get("value"))
        }
        if issn_value not in existing:
            issns.append({"pub_type": "epub", "value": issn_value})
        journal["issns"] = issns
        marked["journal"] = journal
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
    for match in HISTORY_LABEL_RE.finditer("\n".join(lines)):
        date_type = HISTORY_TYPE_MAP.get(match.group("label").lower())
        if not date_type or date_type in seen:
            continue
        parsed = _parse_date_text(match.string[match.end() : match.end() + 80])
        if _blank(parsed.get("year")):
            continue
        history.append({"type": date_type, **parsed})
        seen.add(date_type)
    if history:
        marked["history"] = history
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
            for aff_id in author.get("affiliations") or []:
                if _blank(aff_id):
                    continue
                xref = etree.SubElement(
                    contrib,
                    "xref",
                    attrib={"ref-type": "aff", "rid": str(aff_id).strip()},
                )
                label = None
                for affiliation in data.get("affiliations") or []:
                    if (
                        isinstance(affiliation, dict)
                        and affiliation.get("id") == aff_id
                    ):
                        label = affiliation.get("label")
                        break
                if not _blank(label):
                    _text_el(xref, "sup", label)
            if author.get("corresp"):
                etree.SubElement(
                    contrib, "xref", attrib={"ref-type": "corresp", "rid": "c01"}
                )
            for role in author.get("roles") or []:
                _text_el(contrib, "role", role)

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
        _text_el(notes, "corresp", author_notes.get("corresp"), attrib={"id": "c01"})
        for fn_item in author_notes.get("fns") or []:
            text = fn_item.get("text") if isinstance(fn_item, dict) else fn_item
            _text_el(notes, "fn", text)
        if list(notes):
            article_meta.append(notes)

    for item in data.get("pub_dates") or []:
        if not isinstance(item, dict):
            continue
        date_type = str(item.get("type") or "").strip()
        if date_type not in ("pub", "collection"):
            continue
        pub_date = etree.SubElement(
            article_meta,
            "pub-date",
            attrib={
                "date-type": date_type,
                "publication-format": "electronic",
            },
        )
        if not _append_date_parts(pub_date, item):
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
        and str(item.get("type") or "").strip() in ("received", "rev-recd", "accepted")
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

    permissions = data.get("permissions")
    if isinstance(permissions, dict):
        perm = etree.Element("permissions")
        _text_el(perm, "copyright-statement", permissions.get("copyright_statement"))
        _text_el(perm, "copyright-year", permissions.get("copyright_year"))
        _text_el(perm, "copyright-holder", permissions.get("copyright_holder"))
        href = permissions.get("license_href")
        license_p = permissions.get("license_p")
        if not _blank(href) or not _blank(license_p):
            attrib = {"license-type": "open-access"}
            if not _blank(href):
                attrib["{%s}href" % XLINK_NS] = str(href).strip()
            license_el = etree.SubElement(perm, "license", attrib=attrib)
            _text_el(license_el, "license-p", license_p)
        if list(perm):
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
        raw = mark_front(front_text)
        marked = parse_marked(raw)
        if marked is None:
            preview = str(raw or "")
            logger.warning(
                "Front Llama invalid JSON (%d chars): %r",
                len(preview),
                preview[:500],
            )
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
