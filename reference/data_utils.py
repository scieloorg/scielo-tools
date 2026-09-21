import hashlib
import json
import logging
import re

from django.db import IntegrityError
from lxml import etree

from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)
from reference.marking import mark_reference, mark_reference_texts, mark_references
from reference.models import ElementCitation, Reference, ReferenceStatus
from reference.utils.references import parse_reference_list, stz_norm

logger = logging.getLogger(__name__)

_UNSET = object()


def parse_marked_choice(choice):
    if isinstance(choice, dict):
        return choice
    if not isinstance(choice, str):
        return {"raw": choice}
    text = choice.strip()
    if not text:
        return {"raw": choice}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        parsed = None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            parsed = None
    return {"raw": choice}


def is_non_reference(marked_data):
    return isinstance(marked_data, dict) and marked_data.get("is_reference") is False


meses = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
    "janeiro": "01",
    "fevereiro": "02",
    "março": "03",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def get_number_of_month(texto):
    texto = texto.lower()
    for mes, numero in meses.items():
        if re.search(rf"\b{mes}\b", texto):
            return numero
    return None


def append_citation_pages(root, pages):
    value = str(pages).strip().replace("–", "-").replace("—", "-")
    if not value:
        return
    if "-" in value:
        left, right = [part.strip() for part in value.split("-", 1)]
        if left and right:
            etree.SubElement(root, "fpage").text = left
            etree.SubElement(root, "lpage").text = right
            return
    if value.lower().startswith("e") or (value.isdigit() and len(value) >= 5):
        etree.SubElement(root, "elocation-id").text = value
        return
    etree.SubElement(root, "fpage").text = value


def append_fpage_lpage(root, json_reference):
    if "fpage" in json_reference:
        etree.SubElement(root, "fpage").text = str(json_reference["fpage"])
        if "lpage" in json_reference:
            etree.SubElement(root, "lpage").text = str(json_reference["lpage"])
        return True
    if "pages" in json_reference:
        append_citation_pages(root, json_reference["pages"])
        return True
    return False


def normalize_doi(doi):
    value = str(doi).strip()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :].strip()
            break
    return value.rstrip(".,;:)]}»\"'")


_DOI_URL_RE = re.compile(
    r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)
_DOI_LABEL_RE = re.compile(
    r"\bdoi:\s*(10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)
_DOI_BARE_RE = re.compile(
    r"(?<![A-Za-z0-9])(10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)


def extract_doi_from_text(text):
    if not text:
        return None
    for pattern in (_DOI_URL_RE, _DOI_LABEL_RE, _DOI_BARE_RE):
        match = pattern.search(str(text))
        if match:
            return normalize_doi(match.group(1))
    return None


_URI_RE = re.compile(r"(?:https?|ftp)://[^\s<>\"')\]]+", re.IGNORECASE)


def normalize_uri(uri):
    if uri is None:
        return None
    return str(uri).strip().rstrip(".,;:)]}»\"'")


def extract_uri_from_text(text, allow_doi=True):
    if not text:
        return None
    for match in _URI_RE.finditer(str(text)):
        uri = normalize_uri(match.group(0))
        if not uri:
            continue
        if not allow_doi and "doi.org/" in uri.lower():
            continue
        return uri
    return None


_VOL_ISSUE_PAGES_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,4})\s*\(\s*(\d{1,4})\s*\)\s*"
    r"(?::|,)\s*([eE]?\d+)\s*[–—-]\s*([eE]?\d+)"
)
_VOL_ISSUE_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,4})\s*\(\s*(\d{1,4})\s*\)\s*(?::|,)")
_ISSUE_LABEL_RE = re.compile(
    r"\b(?:n[oº°]\.?|núm(?:ero)?\.?|no\.?|nr\.?|number\.?|issue\.?)\s*" r"(\d{1,4})\b",
    re.IGNORECASE,
)


def extract_vol_num_from_text(text):
    if not text:
        return {}
    value = str(text)
    match = _VOL_ISSUE_PAGES_RE.search(value) or _VOL_ISSUE_RE.search(value)
    if match:
        fields = {
            "vol": int(match.group(1)),
            "num": int(match.group(2)),
        }
        if match.lastindex and match.lastindex >= 4:
            fields["fpage"] = match.group(3)
            fields["lpage"] = match.group(4)
        return fields
    label = _ISSUE_LABEL_RE.search(value)
    if label:
        return {"num": int(label.group(1))}
    return {}


def _missing(value):
    return value in (None, "")


_WEB_LIKE = ("webpage", "software", "database", "legal-doc")


def enrich_marked_from_citation(marked_data, mixed_citation):
    if not isinstance(marked_data, dict) or is_non_reference(marked_data):
        return marked_data
    marked = dict(marked_data)
    reftype = marked.get("reftype")

    doi = marked.get("doi")
    if doi not in (None, ""):
        marked["doi"] = normalize_doi(str(doi))
        doi = marked["doi"]
    else:
        doi = None
    if not doi:
        found = extract_doi_from_text(mixed_citation)
        if not found:
            uri = marked.get("uri")
            if uri and "doi.org/" in str(uri).lower():
                found = normalize_doi(str(uri))
        if found and reftype not in _WEB_LIKE:
            marked["doi"] = found
            doi = found
    if doi:
        uri = marked.get("uri")
        if uri and "doi.org/" in str(uri).lower():
            marked.pop("uri", None)

    extracted = extract_vol_num_from_text(mixed_citation)
    for key in ("vol", "num", "fpage", "lpage"):
        if key in extracted and _missing(marked.get(key)):
            marked[key] = extracted[key]

    if _missing(marked.get("uri")):
        found_uri = extract_uri_from_text(
            mixed_citation,
            allow_doi=reftype in _WEB_LIKE,
        )
        if found_uri:
            if "doi.org/" in found_uri.lower() and reftype not in _WEB_LIKE:
                if _missing(marked.get("doi")):
                    marked["doi"] = normalize_doi(found_uri)
            elif "doi.org/" in found_uri.lower() and not _missing(marked.get("doi")):
                pass
            else:
                marked["uri"] = found_uri
    elif marked.get("uri"):
        marked["uri"] = normalize_uri(marked["uri"])

    return marked


def marked_gained_fields(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    for key in ("doi", "num", "vol", "fpage", "lpage", "uri"):
        if not _missing(after.get(key)) and _missing(before.get(key)):
            return True
    if before.get("uri") and "uri" not in after and after.get("doi"):
        return True
    return False


def append_doi(root, doi):
    value = normalize_doi(doi)
    if not value:
        return
    etree.SubElement(root, "pub-id", attrib={"pub-id-type": "doi"}).text = value


def append_person_group(root, people, person_group_type):
    person_group = etree.SubElement(
        root,
        "person-group",
        attrib={"person-group-type": person_group_type},
    )
    for person in people:
        if "collab" in person and "surname" not in person and "fname" not in person:
            etree.SubElement(person_group, "collab").text = person["collab"]
            continue
        name = etree.Element("name")
        if "surname" in person:
            etree.SubElement(name, "surname").text = person["surname"]
        if "fname" in person:
            etree.SubElement(name, "given-names").text = person["fname"]
        if "collab" in person:
            etree.SubElement(name, "collab").text = person["collab"]
        person_group.append(name)


def append_num_pages(root, num_pages):
    value = str(num_pages).strip()
    if not value:
        return
    digits = re.search(r"\d+", value)
    size = etree.SubElement(root, "size", attrib={"units": "pages"})
    size.text = digits.group() if digits else value


def append_ext_link(root, uri):
    etree.SubElement(
        root,
        "ext-link",
        attrib={
            "ext-link-type": "uri",
            "{http://www.w3.org/1999/xlink}href": uri,
        },
    ).text = uri


def append_access_date(root, access_date):
    match = re.search(r"\b\d{4}\b", access_date)
    if not match:
        etree.SubElement(
            root,
            "date-in-citation",
            attrib={"content-type": "access-date"},
        ).text = access_date
        return
    year = match.group()
    month = get_number_of_month(access_date) or "01"
    etree.SubElement(
        root,
        "date-in-citation",
        attrib={
            "content-type": "access-date",
            "iso-8601-date": year + "-" + month + "-00",
        },
    ).text = access_date


def get_xml(json_reference):
    try:
        json_reference = json.loads(json_reference)
    except json.JSONDecodeError as exc:
        logger.error("Malformed JSON from IA: %s", exc)
        return etree.Element("error")

    reftype = json_reference.get("reftype")
    if not reftype:
        logger.error("Missing reftype in IA JSON: %s", json_reference)
        return etree.Element("error")

    needs_xlink = reftype in (
        "webpage",
        "data",
        "software",
        "database",
    ) or bool(json_reference.get("uri"))
    if needs_xlink:
        root = etree.Element(
            "element-citation",
            attrib={"publication-type": reftype},
            nsmap={"xlink": "http://www.w3.org/1999/xlink"},
        )
    else:
        root = etree.Element(
            "element-citation",
            attrib={"publication-type": reftype},
        )

    if "authors" in json_reference:
        append_person_group(root, json_reference["authors"], "author")
    if "editors" in json_reference:
        append_person_group(root, json_reference["editors"], "editor")

    if reftype == "journal":
        if "title" in json_reference:
            etree.SubElement(root, "article-title").text = json_reference["title"]
        if "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        if "vol" in json_reference:
            etree.SubElement(root, "volume").text = str(json_reference["vol"])
        if "num" in json_reference:
            etree.SubElement(root, "issue").text = str(json_reference["num"])
        append_fpage_lpage(root, json_reference)
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])

    if reftype == "book":
        chapter = json_reference.get("chapter") or json_reference.get("chapter_title")
        if chapter:
            etree.SubElement(root, "part-title").text = chapter
        if "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        elif "title" in json_reference and not chapter:
            etree.SubElement(root, "source").text = json_reference["title"]
        if "edition" in json_reference:
            etree.SubElement(root, "edition").text = str(json_reference["edition"])
        if "vol" in json_reference:
            etree.SubElement(root, "volume").text = str(json_reference["vol"])
        append_fpage_lpage(root, json_reference)
        if "organization" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference[
                "organization"
            ]
        elif "publisher" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference["publisher"]
        publisher_loc = json_reference.get("location") or json_reference.get(
            "org_location"
        )
        if publisher_loc:
            etree.SubElement(root, "publisher-loc").text = publisher_loc
        if "num_pages" in json_reference:
            append_num_pages(root, json_reference["num_pages"])
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])

    if reftype == "thesis":
        if "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        elif "title" in json_reference:
            etree.SubElement(root, "source").text = json_reference["title"]
        if "degree" in json_reference:
            etree.SubElement(
                root, "comment", attrib={"content-type": "degree"}
            ).text = json_reference["degree"]
        if "organization" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference[
                "organization"
            ]
        if "location" in json_reference:
            etree.SubElement(root, "publisher-loc").text = json_reference["location"]
        if "num_pages" in json_reference:
            append_num_pages(root, json_reference["num_pages"])

    if reftype == "confproc":
        if "title" in json_reference:
            etree.SubElement(root, "conf-name").text = json_reference["title"]
        elif "conf_name" in json_reference:
            etree.SubElement(root, "conf-name").text = json_reference["conf_name"]
        if "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        conf_loc = json_reference.get("conf_loc") or json_reference.get("location")
        if conf_loc:
            etree.SubElement(root, "conf-loc").text = conf_loc
        if "conf_date" in json_reference:
            etree.SubElement(root, "conf-date").text = str(json_reference["conf_date"])
        conf_num = json_reference.get("conf_num")
        if conf_num is None and "num" in json_reference:
            conf_num = json_reference["num"]
        if conf_num is not None:
            etree.SubElement(root, "conf-num").text = str(conf_num)
        if "organization" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference[
                "organization"
            ]
        if "org_location" in json_reference:
            etree.SubElement(root, "publisher-loc").text = json_reference[
                "org_location"
            ]
        if "num_pages" in json_reference:
            append_num_pages(root, json_reference["num_pages"])
        elif "pages" in json_reference and "fpage" not in json_reference:
            append_num_pages(root, json_reference["pages"])
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])

    if reftype == "data":
        if "title" in json_reference:
            etree.SubElement(root, "data-title").text = json_reference["title"]
        if "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        if "version" in json_reference:
            etree.SubElement(root, "version").text = str(json_reference["version"])
        if "uri" in json_reference:
            append_ext_link(root, json_reference["uri"])
        if "organization" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference[
                "organization"
            ]
        if "location" in json_reference:
            etree.SubElement(root, "publisher-loc").text = json_reference["location"]
        if "access_id" in json_reference:
            etree.SubElement(root, "comment").text = str(json_reference["access_id"])
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])
        if "access_date" in json_reference:
            append_access_date(root, json_reference["access_date"])

    if reftype in ("webpage", "software", "database", "legal-doc"):
        if "title" in json_reference:
            etree.SubElement(root, "source").text = json_reference["title"]
        elif "source" in json_reference and root.find("source") is None:
            etree.SubElement(root, "source").text = json_reference["source"]
        if "uri" in json_reference:
            append_ext_link(root, json_reference["uri"])
        if "organization" in json_reference:
            etree.SubElement(root, "publisher-name").text = json_reference[
                "organization"
            ]
        publisher_loc = (
            json_reference.get("location")
            or json_reference.get("country")
            or json_reference.get("org_location")
        )
        if publisher_loc:
            etree.SubElement(root, "publisher-loc").text = publisher_loc
        if "version" in json_reference and reftype == "software":
            etree.SubElement(root, "version").text = str(json_reference["version"])
        if "access_id" in json_reference:
            etree.SubElement(root, "comment").text = str(json_reference["access_id"])
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])
        if "access_date" in json_reference:
            append_access_date(root, json_reference["access_date"])

    if reftype == "other":
        if "title" in json_reference:
            etree.SubElement(root, "source").text = json_reference["title"]
        elif "source" in json_reference:
            etree.SubElement(root, "source").text = json_reference["source"]
        if "doi" in json_reference:
            append_doi(root, json_reference["doi"])
        if "uri" in json_reference:
            append_ext_link(root, json_reference["uri"])

    if "date" in json_reference:
        etree.SubElement(root, "year").text = str(json_reference["date"])

    if json_reference.get("doi") and root.find("pub-id[@pub-id-type='doi']") is None:
        append_doi(root, json_reference["doi"])

    if (
        json_reference.get("uri")
        and root.find("ext-link") is None
        and root.find("pub-id[@pub-id-type='doi']") is None
    ):
        append_ext_link(root, json_reference["uri"])

    return root


def build_ref_list(results):
    root = etree.Element("ref-list")
    etree.SubElement(root, "title").text = "References"

    for index, item in enumerate(results, start=1):
        ref = etree.SubElement(root, "ref", attrib={"id": f"B{index}"})
        mixed = etree.SubElement(ref, "mixed-citation")
        mixed.text = item.get("mixed_citation") or ""

        marked_xml = item.get("data") or ""
        if not marked_xml:
            logger.warning("Missing element-citation XML for ref B%s", index)
            continue
        try:
            citation_node = etree.fromstring(marked_xml.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            logger.warning("Invalid element-citation XML for ref B%s: %s", index, exc)
            continue
        if citation_node.tag == "error":
            logger.warning("Error element-citation for ref B%s", index)
            continue
        ref.append(citation_node)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


def resolve_reference_result(
    mixed_citation, user=None, output_type="json", marked_data=_UNSET
):
    normalized = stz_norm(mixed_citation)
    checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    try:
        reference = Reference.objects.get(checksum=checksum)
    except Reference.DoesNotExist:
        if marked_data is _UNSET:
            marked_data = None
            for choice in mark_reference(mixed_citation):
                marked_data = parse_marked_choice(choice)
                break
        if marked_data is None or is_non_reference(marked_data):
            logger.info("Ignoring non-reference input: %r", mixed_citation)
            return None
        marked_data = enrich_marked_from_citation(marked_data, mixed_citation)
        if not marked_data.get("reftype"):
            logger.info(
                "Ignoring mark without reftype: %r marked=%s",
                mixed_citation,
                marked_data,
            )
            return None
        try:
            reference, created = Reference.objects.get_or_create(
                checksum=checksum,
                defaults={
                    "mixed_citation": mixed_citation,
                    "status": ReferenceStatus.CREATING,
                    "creator": user,
                },
            )
        except IntegrityError:
            reference = Reference.objects.get(checksum=checksum)
            created = False
        if created or not reference.element_citation.exists():
            ElementCitation.objects.create(
                reference=reference,
                marked=marked_data,
                marked_xml=etree.tostring(
                    get_xml(json.dumps(marked_data)),
                    pretty_print=True,
                    encoding="unicode",
                ),
            )
            reference.status = ReferenceStatus.READY
            reference.save()

    element = reference.element_citation.first()
    marked = element.marked if element else {}
    if isinstance(marked, dict):
        enriched = enrich_marked_from_citation(marked, reference.mixed_citation)
        if marked_gained_fields(marked, enriched):
            marked_xml = etree.tostring(
                get_xml(json.dumps(enriched)),
                pretty_print=True,
                encoding="unicode",
            )
            element.marked = enriched
            element.marked_xml = marked_xml
            element.save(update_fields=["marked", "marked_xml"])
            marked = enriched
    if output_type in ("xml", "jats"):
        data = element.marked_xml if element else ""
    else:
        data = marked if element else {}

    return {
        "mixed_citation": reference.mixed_citation,
        "data": data,
    }


def resolve_references_result(references, user=None, output_type="json"):
    citations = parse_reference_list(references)
    pending = []
    pending_seen = set()
    for citation in citations:
        checksum = hashlib.sha256(stz_norm(citation).encode("utf-8")).hexdigest()
        if Reference.objects.filter(checksum=checksum).exists():
            continue
        if citation in pending_seen:
            continue
        pending_seen.add(citation)
        pending.append(citation)

    premarked = {}
    if pending:
        marked_pending = mark_reference_texts(pending)
        for citation, content in zip(pending, marked_pending, strict=False):
            premarked[citation] = (
                parse_marked_choice(content) if content is not None else None
            )

    results = []
    for citation in citations:
        if citation in premarked:
            item = resolve_reference_result(
                citation,
                user=user,
                output_type=output_type,
                marked_data=premarked[citation],
            )
        else:
            item = resolve_reference_result(
                citation, user=user, output_type=output_type
            )
        if item is not None:
            results.append(item)
    return results


def get_reference(obj_id):
    logger.info("Starting get_reference for ID=%s", obj_id)
    obj_reference = Reference.objects.get(id=obj_id)
    try:
        logger.info("Marking citation: %r", obj_reference.mixed_citation)
        marked = list(mark_references(obj_reference.mixed_citation))

        citations_created = 0
        for item in marked:
            for i in item["choices"]:
                marked_data = enrich_marked_from_citation(
                    parse_marked_choice(i),
                    item.get("references") or obj_reference.mixed_citation,
                )
                if is_non_reference(marked_data):
                    logger.info(
                        "Skipping non-reference mark for ID=%s: %r",
                        obj_id,
                        item.get("references"),
                    )
                    continue
                if not marked_data.get("reftype") and "raw" not in marked_data:
                    logger.info(
                        "Skipping mark without reftype for ID=%s: %s",
                        obj_id,
                        marked_data,
                    )
                    continue
                citation = ElementCitation.objects.create(
                    reference=obj_reference,
                    marked=marked_data,
                    marked_xml=etree.tostring(
                        get_xml(json.dumps(marked_data)),
                        pretty_print=True,
                        encoding="unicode",
                    ),
                )
                citations_created += 1
                logger.debug(
                    "Created ElementCitation ID=%s for marked citation: %s",
                    citation.pk,
                    i,
                )

        if citations_created == 0:
            logger.info(
                "No bibliographic citations for ID=%s; deleting Reference",
                obj_id,
            )
            obj_reference.delete()
            return

        obj_reference.status = ReferenceStatus.READY
        obj_reference.save()
        logger.info(
            "get_reference completed for ID=%s. Citations created: %d",
            obj_id,
            citations_created,
        )
    except (
        ReferenceLlamaDisabledError,
        ReferenceLlamaMisconfiguredError,
        ReferenceLlamaUnavailableError,
    ) as exc:
        logger.error(
            "Llama unavailable in get_reference for ID=%s: %s — deleting Reference",
            obj_id,
            exc,
        )
        obj_reference.delete()
        raise
    except Exception as exc:
        logger.error("Error in get_reference for ID=%s: %s", obj_id, exc, exc_info=True)
        raise
