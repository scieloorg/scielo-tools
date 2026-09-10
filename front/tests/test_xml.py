from lxml import etree

from front.data_utils import apply_language_fallback, get_front_xml

SPS_FRONT_TAGS = {
    "front",
    "journal-meta",
    "journal-id",
    "journal-title-group",
    "journal-title",
    "abbrev-journal-title",
    "issn",
    "publisher",
    "publisher-name",
    "article-meta",
    "article-id",
    "article-categories",
    "subj-group",
    "subject",
    "title-group",
    "article-title",
    "trans-title-group",
    "trans-title",
    "contrib-group",
    "contrib",
    "contrib-id",
    "name",
    "surname",
    "given-names",
    "collab",
    "xref",
    "sup",
    "role",
    "aff",
    "label",
    "institution",
    "addr-line",
    "city",
    "state",
    "postal-code",
    "country",
    "email",
    "author-notes",
    "corresp",
    "fn",
    "pub-date",
    "day",
    "month",
    "year",
    "season",
    "volume",
    "issue",
    "fpage",
    "lpage",
    "elocation-id",
    "history",
    "date",
    "permissions",
    "copyright-statement",
    "copyright-year",
    "copyright-holder",
    "license",
    "license-p",
    "abstract",
    "trans-abstract",
    "title",
    "p",
    "sec",
    "kwd-group",
    "kwd",
    "funding-group",
    "award-group",
    "funding-source",
    "award-id",
    "funding-statement",
    "counts",
    "fig-count",
    "table-count",
    "equation-count",
    "ref-count",
}

SAMPLE_MARKED = {
    "journal": {
        "journal_ids": [
            {"type": "publisher-id", "value": "bn"},
            {"type": "nlm-ta", "value": "Biota Neotropica"},
        ],
        "journal_title": "Biota Neotropica",
        "abbrev_journal_title": "Biota Neotrop.",
        "issns": [{"pub_type": "epub", "value": "1676-0611"}],
        "publisher_name": "Instituto Virtual da Biodiversidade",
    },
    "article_ids": [
        {
            "pub_id_type": "doi",
            "value": "https://doi.org/10.1590/1676-0611-BN-2025-1870",
        }
    ],
    "categories": [{"subject": "Article"}],
    "titles": [
        {"kind": "main", "text": "Main title", "language": "en"},
        {"kind": "translated", "language": "pt", "text": "Título traduzido"},
    ],
    "authors": [
        {
            "contrib_type": "author",
            "given_names": "Jéssica S. de",
            "surname": "Lima",
            "orcid": "https://orcid.org/0000-0002-3193-9315",
            "affiliations": ["aff1"],
            "corresp": True,
            "roles": ["Writing the original draft"],
        }
    ],
    "affiliations": [
        {
            "id": "aff1",
            "label": "1",
            "original": "Instituto de Pesquisas Ambientais, São Paulo, SP, Brasil.",
            "orgname": "Instituto de Pesquisas Ambientais",
            "city": "São Paulo",
            "state": "SP",
            "country": "Brasil",
        }
    ],
    "author_notes": {"corresp": "* Correspondence: jessica@example.com"},
    "pub_dates": [
        {"type": "pub", "day": "01", "month": "01", "year": "2026"},
        {"type": "collection", "year": "2026"},
    ],
    "volume": "26",
    "issue": "2",
    "elocation_id": "e20251870",
    "history": [
        {"type": "received", "day": "10", "month": "01", "year": "2025"},
        {"type": "accepted", "day": "21", "month": "04", "year": "2026"},
    ],
    "permissions": {
        "license_href": "https://creativecommons.org/licenses/by/4.0/",
        "license_p": "This is an Open Access article.",
    },
    "abstracts": [
        {"kind": "main", "title": "Abstract", "text": "This study reports bryophytes."},
        {
            "kind": "translated",
            "language": "pt",
            "title": "Resumo",
            "text": "Este estudo relata briófitas.",
        },
    ],
    "keywords": [
        {
            "language": "en",
            "title": "Keywords",
            "keywords": ["Amazon flora", "Herbarium"],
        },
        {
            "language": "pt",
            "title": "Palavras-chave",
            "keywords": ["Flora amazônica", "Herbário"],
        },
    ],
    "funding": {
        "awards": [{"funding_source": "FAPESP", "award_id": "2024/23894-1"}],
        "funding_statement": "Processo FAPESP 2024/23894-1.",
    },
    "counts": {"fig_count": "03", "ref_count": "52"},
}


def test_get_front_xml_is_complete_front():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag == "front"
    assert root.find("journal-meta") is not None
    assert root.find("article-meta") is not None


def test_get_front_xml_only_sps_tags():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    found = {node.tag.split("}")[-1] for node in root.iter()}
    unexpected = found - SPS_FRONT_TAGS
    assert not unexpected, unexpected


def test_get_front_xml_article_title_and_abstract_have_no_lang():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    article_title = root.find(".//article-title")
    abstract = root.find(".//abstract")
    xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
    assert xml_lang not in article_title.attrib
    assert xml_lang not in abstract.attrib
    trans_title_group = root.find(".//trans-title-group")
    trans_abstract = root.find(".//trans-abstract")
    assert trans_title_group.get(xml_lang) == "pt"
    assert trans_abstract.get(xml_lang) == "pt"


def test_get_front_xml_normalizes_doi_orcid_and_country():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    doi = root.find(".//article-id[@pub-id-type='doi']")
    assert doi.text == "10.1590/1676-0611-BN-2025-1870"
    orcid = root.find(".//contrib-id[@contrib-id-type='orcid']")
    assert orcid.text == "0000-0002-3193-9315"
    country = root.find(".//aff/country")
    assert country.get("country") == "BR"
    assert country.text == "Brasil"


def test_get_front_xml_omits_missing_optional_tags():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Only a title"}],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag == "front"
    assert root.find("journal-meta") is None
    assert root.find("article-meta/title-group/article-title").text == "Only a title"
    assert root.find(".//volume") is None
    assert root.find(".//funding-group") is None
    assert root.find(".//counts") is None
    assert root.find(".//abstract") is None


def test_get_front_xml_ignores_unknown_journal_id_type():
    xml = get_front_xml(
        {
            "journal": {
                "journal_ids": [{"type": "invented", "value": "xxx"}],
                "journal_title": "Journal",
            }
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(".//journal-id") is None
    assert root.find(".//journal-title").text == "Journal"


def test_apply_language_fallback_fills_keyword_language():
    marked = apply_language_fallback(
        {"keywords": [{"keywords": ["ciência"]}]},
        "pt",
    )
    assert marked["keywords"][0]["language"] == "pt"
