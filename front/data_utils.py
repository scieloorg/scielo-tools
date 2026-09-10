import hashlib
import json
import re

from django.db import IntegrityError
from lxml import etree

from front.exceptions import FrontLlamaUnavailableError
from front.marking import mark_front
from front.models import Front
from front.utils import normalize_front_text

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


def _blank(value):
    return value is None or str(value).strip() == ""


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


def _date_parts(item):
    if not isinstance(item, dict):
        return {}
    parts = {
        "day": item.get("day"),
        "month": item.get("month"),
        "year": item.get("year"),
        "season": item.get("season"),
    }
    raw = item.get("date")
    if _blank(parts["year"]) and not _blank(raw):
        match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", str(raw).strip())
        if match:
            parts["year"] = match.group(1)
            parts["month"] = match.group(2) or parts["month"]
            parts["day"] = match.group(3) or parts["day"]
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
    try:
        parsed = json.loads(choice)
    except (TypeError, json.JSONDecodeError):
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
            group = etree.SubElement(
                article_categories,
                "subj-group",
                attrib={"subj-group-type": "heading"},
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
        words = [word for word in (group.get("keywords") or []) if not _blank(word)]
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


def resolve_front_result(front_text, user=None, output_type="json", language=None):
    normalized = normalize_front_text(front_text)
    checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    try:
        record = Front.objects.get(checksum=checksum)
    except Front.DoesNotExist:
        raw = mark_front(front_text)
        marked = parse_marked(raw)
        if marked is None:
            raise FrontLlamaUnavailableError("Front Llama returned invalid JSON")
        marked = apply_language_fallback(marked, language)
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

    if output_type == "xml":
        data = record.marked_xml
    else:
        data = record.marked
    return {"data": data}
