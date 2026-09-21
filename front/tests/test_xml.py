import pytest
from lxml import etree

from front.data_utils import (
    apply_language_fallback,
    apply_text_fields,
    get_front_xml,
    parse_marked,
)

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


def test_get_front_xml_maps_credit_role_and_defaults_aff_xref():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "authors": [
                {
                    "given_names": "Karoline A.F.",
                    "surname": "Ribeiro",
                    "roles": ["study design", "initial draft preparation"],
                }
            ],
            "affiliations": [
                {
                    "id": "aff1",
                    "label": "1",
                    "orgname": "Instituto Mamirauá",
                }
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    contrib = root.find(".//contrib")
    xref = contrib.find("xref[@ref-type='aff']")
    assert xref.get("rid") == "aff1"
    assert xref.find("sup").text == "1"
    roles = contrib.findall("role")
    assert [role.text for role in roles] == [
        "Conceptualization",
        "Writing – original draft",
    ]
    assert roles[0].get("content-type") == (
        "https://credit.niso.org/contributor-roles/conceptualization/"
    )
    assert roles[1].get("content-type") == (
        "https://credit.niso.org/contributor-roles/writing-original-draft/"
    )


def test_get_front_xml_resolves_numeric_affiliation_ids():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "authors": [
                {
                    "given_names": "Leonardo P.",
                    "surname": "Reis",
                    "affiliations": ["1", "aff2"],
                }
            ],
            "affiliations": [
                {"id": "aff1", "label": "1", "orgname": "IDSM"},
                {"id": "aff2", "label": "2", "orgname": "UFRA"},
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    rids = [
        xref.get("rid") for xref in root.findall(".//contrib/xref[@ref-type='aff']")
    ]
    assert rids == ["aff1", "aff2"]


def test_get_front_xml_fills_collection_year_without_placeholder_pub_date():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "history": [
                {"type": "received", "day": "05", "month": "08", "year": "2025"},
                {"type": "accepted", "day": "27", "month": "03", "year": "2026"},
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(".//pub-date[@date-type='pub']") is None
    collection = root.find(".//pub-date[@date-type='collection']")
    assert collection.get("publication-format") == "electronic"
    assert collection.find("year").text == "2026"
    assert collection.find("month") is None
    assert collection.find("day") is None


def test_get_front_xml_omits_incomplete_electronic_pub_date():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "pub_dates": [
                {"type": "pub", "day": "00", "month": "00", "year": "2025"},
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(".//pub-date[@date-type='pub']") is None
    collection = root.find(".//pub-date[@date-type='collection']")
    assert collection.find("year").text == "2025"


def test_get_front_xml_keeps_explicit_pub_dates():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    pub = root.find(".//pub-date[@date-type='pub']")
    assert pub.find("day").text == "01"
    assert pub.find("month").text == "01"
    assert pub.find("year").text == "2026"
    roles = root.findall(".//contrib/role")
    assert roles[0].text == "Writing – original draft"
    assert roles[0].get("content-type") == (
        "https://credit.niso.org/contributor-roles/writing-original-draft/"
    )


def test_get_front_xml_emits_history_rev_request_and_pub():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "history": [
                {"type": "received", "day": "05", "month": "08", "year": "2025"},
                {"type": "rev-request", "day": "10", "month": "10", "year": "2025"},
                {"type": "rev-recd", "day": "01", "month": "02", "year": "2026"},
                {"type": "accepted", "day": "27", "month": "03", "year": "2026"},
                {"type": "pub", "day": "15", "month": "05", "year": "2026"},
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    types = [el.get("date-type") for el in root.findall(".//history/date")]
    assert types == [
        "received",
        "rev-request",
        "rev-recd",
        "accepted",
        "pub",
    ]


def test_get_front_xml_emits_counts_including_zero():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "counts": {
                "fig_count": "8",
                "table_count": "1",
                "equation_count": "0",
                "ref_count": "23",
            },
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    counts = root.find(".//counts")
    assert counts.find("fig-count").get("count") == "8"
    assert counts.find("table-count").get("count") == "1"
    assert counts.find("equation-count").get("count") == "0"
    assert counts.find("ref-count").get("count") == "23"


def test_get_front_xml_history_parses_day_month_year_and_swaps_invalid_month():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "history": [
                {"type": "received", "date": "22/12/2025"},
                {
                    "type": "accepted",
                    "day": "04",
                    "month": "21",
                    "year": "2026",
                },
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    received = root.find(".//date[@date-type='received']")
    assert received.find("day").text == "22"
    assert received.find("month").text == "12"
    assert received.find("year").text == "2025"
    accepted = root.find(".//date[@date-type='accepted']")
    assert accepted.find("day").text == "21"
    assert accepted.find("month").text == "04"
    assert accepted.find("year").text == "2026"


def test_get_front_xml_omits_null_history_parts():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "history": [
                {
                    "type": "received",
                    "day": "null",
                    "month": "null",
                    "year": "null",
                },
                {
                    "type": "accepted",
                    "day": "21",
                    "month": "04",
                    "year": "2026",
                },
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(".//date[@date-type='received']") is None
    accepted = root.find(".//date[@date-type='accepted']")
    assert accepted.find("day").text == "21"
    assert accepted.find("month").text == "04"
    assert accepted.find("year").text == "2026"


@pytest.mark.parametrize(
    "item,day,month,year",
    [
        ({"type": "received", "date": "23 Sept. 2025"}, "23", "09", "2025"),
        ({"type": "accepted", "date": "09 Dec. 2025"}, "09", "12", "2025"),
        ({"type": "received", "date": "23 09 2025"}, "23", "09", "2025"),
        ({"type": "accepted", "date": "09 12 2025"}, "09", "12", "2025"),
        ({"type": "received", "date": "23 de setembro de 2025"}, "23", "09", "2025"),
        ({"type": "accepted", "date": "09 de dezembro de 2025"}, "09", "12", "2025"),
        ({"type": "received", "date": "23 de septiembre de 2025"}, "23", "09", "2025"),
        ({"type": "received", "date": "23 de set. de 2025"}, "23", "09", "2025"),
        (
            {"type": "received", "date": "the 23rd of September 2025"},
            "23",
            "09",
            "2025",
        ),
        ({"type": "received", "date": "16 de novembro de 2025"}, "16", "11", "2025"),
        ({"type": "received", "date": "18 June 2025"}, "18", "06", "2025"),
        ({"type": "accepted", "date": "11 December 2025"}, "11", "12", "2025"),
        ({"type": "received", "date": "July 07, 2025"}, "07", "07", "2025"),
        ({"type": "accepted", "date": "January 05, 2026"}, "05", "01", "2026"),
        ({"type": "received", "date": "November 6, 2025"}, "06", "11", "2025"),
        ({"type": "received", "date": "01 Dec. 2025"}, "01", "12", "2025"),
        ({"type": "accepted", "date": "24 Feb. 2026"}, "24", "02", "2026"),
        ({"type": "received", "date": "15 August 2025"}, "15", "08", "2025"),
        ({"type": "received", "date": "19 de agosto de 2025"}, "19", "08", "2025"),
        ({"type": "accepted", "date": "03 de janeiro de 2026"}, "03", "01", "2026"),
        ({"type": "received", "date": "23/09/2025"}, "23", "09", "2025"),
        ({"type": "received", "date": "2025-09-23"}, "23", "09", "2025"),
        ({"type": "accepted", "date": "01/29/2026"}, "29", "01", "2026"),
        (
            {"type": "received", "day": "23", "month": "Sept", "year": "2025"},
            "23",
            "09",
            "2025",
        ),
        (
            {"type": "accepted", "day": "09", "month": "dezembro", "year": "2025"},
            "09",
            "12",
            "2025",
        ),
    ],
)
def test_get_front_xml_parses_history_date_formats(item, day, month, year):
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "history": [item],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    date = root.find(f".//date[@date-type='{item['type']}']")
    assert date.find("day").text == day
    assert date.find("month").text == month
    assert date.find("year").text == year


def test_get_front_xml_splits_semicolon_keywords():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "keywords": [
                {
                    "language": "en",
                    "title": "Keywords",
                    "keywords": ["amazon flora; collections; herbarium; mosses."],
                }
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    words = [kwd.text for kwd in root.findall(".//kwd")]
    assert words == ["amazon flora", "collections", "herbarium", "mosses"]


def test_get_front_xml_subj_group_type_defaults_to_heading():
    xml = get_front_xml(SAMPLE_MARKED)
    root = etree.fromstring(xml.encode("utf-8"))
    group = root.find(".//subj-group")
    assert group.get("subj-group-type") == "heading"
    assert group.find("subject").text == "Article"


def test_get_front_xml_uses_subj_group_type_from_marked():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "categories": [
                {
                    "subj_group_type": "heading",
                    "subject": "Short Communication",
                }
            ],
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    group = root.find(".//subj-group")
    assert group.get("subj-group-type") == "heading"
    assert group.find("subject").text == "Short Communication"


def test_get_front_xml_always_emits_cc_by_40_permissions():
    xml = get_front_xml({"titles": [{"kind": "main", "text": "Title"}]})
    root = etree.fromstring(xml.encode("utf-8"))
    license_el = root.find(".//article-meta/permissions/license")
    xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
    xlink_href = "{http://www.w3.org/1999/xlink}href"
    assert license_el.get("license-type") == "open-access"
    assert license_el.get(xlink_href) == "https://creativecommons.org/licenses/by/4.0/"
    assert license_el.get(xml_lang) == "en"
    assert license_el.find("license-p").text == (
        "This is an Open Access article distributed under the terms of the "
        "Creative Commons Attribution License, which permits unrestricted use, "
        "distribution, and reproduction in any medium, provided the original "
        "work is properly cited."
    )


def test_get_front_xml_ignores_marked_license_text():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "permissions": {
                "license_href": "https://creativecommons.org/licenses/by-nc/4.0/",
                "license_p": "This is an Open Access article.",
            },
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    license_el = root.find(".//article-meta/permissions/license")
    xlink_href = "{http://www.w3.org/1999/xlink}href"
    assert license_el.get(xlink_href) == "https://creativecommons.org/licenses/by/4.0/"
    assert "properly cited" in license_el.find("license-p").text


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
    assert root.find(".//article-meta/permissions/license") is not None


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


def test_apply_text_fields_reads_masthead_and_keyword_lines():
    text = (
        "Biota Neotropica 26(2): e20251870, 2026\n"
        "www.scielo.br/bn\n"
        "Articles\n"
        "What do scientific collections reveal about the past of the Amazon?\n"
        "Keywords: amazon flora; collections; herbarium; liverworts; mosses.\n"
        "Palavras-chave: flora amazônica; coleções; herbário; hepáticas; musgos."
    )
    marked = apply_text_fields({"titles": [{"kind": "main", "text": "Title"}]}, text)
    assert marked["journal"]["journal_title"] == "Biota Neotropica"
    assert marked["keywords"] == [
        {
            "language": "en",
            "title": "Keywords",
            "keywords": [
                "amazon flora",
                "collections",
                "herbarium",
                "liverworts",
                "mosses",
            ],
        },
        {
            "language": "pt",
            "title": "Palavras-chave",
            "keywords": [
                "flora amazônica",
                "coleções",
                "herbário",
                "hepáticas",
                "musgos",
            ],
        },
    ]


def test_apply_text_fields_reads_journal_name_before_issn():
    text = "Revista Exemplo de Ciências\nISSN 1111-2222\nOriginal Article"
    marked = apply_text_fields({}, text)
    assert marked["journal"]["journal_title"] == "Revista Exemplo de Ciências"
    assert marked["journal"]["issns"] == [{"pub_type": "epub", "value": "1111-2222"}]


def test_apply_text_fields_replaces_llm_issns_with_source():
    text = (
        "Biota Neotropica 26(2): e20251878, 2025\n"
        "https://doi.org/10.1590/1676-0611-BN-2025-1878\n"
        "Short Communication\n"
    )
    marked = apply_text_fields(
        {
            "journal": {
                "journal_title": "Biota Neotropica",
                "issns": [
                    {"pub_type": "ppub", "value": "1111-2222"},
                    {"pub_type": "epub", "value": "3333-4444"},
                ],
            }
        },
        text,
    )
    assert marked["journal"]["issns"] == [{"pub_type": "epub", "value": "1676-0611"}]


def test_apply_text_fields_drops_llm_issns_absent_from_source():
    text = "Original Article\nSeasonal rainfall and forest birds in the Cerrado\n"
    marked = apply_text_fields(
        {
            "journal": {
                "journal_title": "Biota Neotropica",
                "issns": [
                    {"pub_type": "ppub", "value": "1111-2222"},
                    {"pub_type": "epub", "value": "3333-4444"},
                ],
            }
        },
        text,
    )
    assert "issns" not in marked["journal"]
    assert marked["journal"]["journal_title"] == "Biota Neotropica"


def test_apply_text_fields_reads_print_and_online_issn_from_source():
    text = (
        "Revista Exemplo de Ciências\n"
        "ISSN 1414-8145 (Print)\n"
        "ISSN 2177-9465 (Online)\n"
        "Original Article\n"
    )
    marked = apply_text_fields(
        {
            "journal": {
                "issns": [
                    {"pub_type": "ppub", "value": "1111-2222"},
                    {"pub_type": "epub", "value": "3333-4444"},
                ]
            }
        },
        text,
    )
    assert marked["journal"]["issns"] == [
        {"pub_type": "ppub", "value": "1414-8145"},
        {"pub_type": "epub", "value": "2177-9465"},
    ]


def test_apply_text_fields_does_not_use_article_title_as_journal():
    text = (
        "What do scientific collections reveal about the past of the Amazon?\n"
        "Jéssica S. de Lima\n"
        "Abstract: A study."
    )
    marked = apply_text_fields({}, text)
    assert "journal" not in marked


def test_apply_text_fields_fills_missing_orcid_from_name_lines():
    text = (
        "Jéssica S. de Lima https://orcid.org/0000-0002-3193-9315\n"
        "Felipe Gonzatti https://orcid.org/0000-0003-1971-0558\n"
        "Olga Yano http://orcid.org/0009-0005-7077-5260\n"
    )
    marked = apply_text_fields(
        {
            "authors": [
                {
                    "given_names": "Jéssica S. de",
                    "surname": "Lima",
                    "orcid": "0000-0002-3193-9315",
                },
                {"given_names": "Felipe", "surname": "Gonzatti"},
                {"given_names": "Olga", "surname": "Yano"},
            ]
        },
        text,
    )
    authors = marked["authors"]
    assert authors[0]["orcid"] == "0000-0002-3193-9315"
    assert authors[1]["orcid"] == "0000-0003-1971-0558"
    assert authors[2]["orcid"] == "0009-0005-7077-5260"


def test_apply_text_fields_fills_issn_abstracts_and_affiliations():
    text = (
        "Biota Neotropica 26(2): e20251870, 2026\n"
        "www.scielo.br/bn\n"
        "1Instituto de Pesquisas Ambientais, Av. Miguel Stéfano, 3687, "
        "04301-902 São Paulo, SP, Brasil.\n"
        "2Universidade Federal do ABC, Laboratório de Interação Planta-Animal, "
        "Campus de São Bernardo do Campo, São Bernardo do Campo, SP, Brasil.\n"
        "3 Universidade Federal de São Carlos, Centro de Ciências da Natureza, "
        "Campus Lagoa do Sino, Rod. Lauri Simões de Barros, km 12, Buri, SP, Brasil\n"
        "4 Universidade de Caxias do Sul, Museu de Ciências Naturais, "
        "Caxias do Sul, RS, Brasil.\n"
        "https://doi.org/10.1590/1676-0611-BN-2025-1870\n"
        "Abstract: First sentence of the abstract. Second sentence stays.\n"
        "Keywords: mosses.\n"
        "Resumo: Primeira frase do resumo. Segunda frase permanece.\n"
        "Palavras-chave: musgos.\n"
    )
    marked = apply_text_fields({}, text)
    assert marked["journal"]["issns"] == [{"pub_type": "epub", "value": "1676-0611"}]
    assert marked["abstracts"][0]["kind"] == "main"
    assert marked["abstracts"][0]["text"].startswith("First sentence")
    assert "Second sentence stays" in marked["abstracts"][0]["text"]
    assert marked["abstracts"][1]["language"] == "pt"
    assert "Segunda frase permanece" in marked["abstracts"][1]["text"]
    affs = marked["affiliations"]
    assert [item["id"] for item in affs] == ["aff1", "aff2", "aff3", "aff4"]
    assert affs[0]["orgname"] == "Instituto de Pesquisas Ambientais"
    assert affs[0]["city"] == "São Paulo"
    assert affs[0]["state"] == "SP"
    assert affs[0]["country"] == "Brasil"
    assert affs[1]["orgname"] == "Universidade Federal do ABC"
    assert affs[1]["city"] == "São Bernardo do Campo"
    assert affs[1]["orgdiv1"] == "Laboratório de Interação Planta-Animal"
    assert affs[2]["orgname"] == "Universidade Federal de São Carlos"
    assert affs[2]["city"] == "Buri"
    assert affs[3]["orgname"] == "Universidade de Caxias do Sul"
    assert affs[3]["city"] == "Caxias do Sul"


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Received: 23 Sept. 2025\nAccepted: 09 Dec. 2025",
            [
                {
                    "type": "received",
                    "day": "23",
                    "month": "09",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "09",
                    "month": "12",
                    "year": "2025",
                },
            ],
        ),
        (
            "Received: 23 09 2025\nAccepted: 09 12 2025",
            [
                {
                    "type": "received",
                    "day": "23",
                    "month": "09",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "09",
                    "month": "12",
                    "year": "2025",
                },
            ],
        ),
        (
            "Recebido em 16 de novembro de 2025. "
            "Revisado em 29 de novembro de 2025. "
            "Aceito em 03 de janeiro de 2026.",
            [
                {
                    "type": "received",
                    "day": "16",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "rev-recd",
                    "day": "29",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "03",
                    "month": "01",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received: July 07, 2025; Accepted: January 05, 2026.",
            [
                {
                    "type": "received",
                    "day": "07",
                    "month": "07",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "05",
                    "month": "01",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received: 18 June 2025; Accepted: 11 December 2025",
            [
                {
                    "type": "received",
                    "day": "18",
                    "month": "06",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "11",
                    "month": "12",
                    "year": "2025",
                },
            ],
        ),
        (
            "Submitted on 11/06/2025.Accepted on 03/05/2026.",
            [
                {
                    "type": "received",
                    "day": "11",
                    "month": "06",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "03",
                    "month": "05",
                    "year": "2026",
                },
            ],
        ),
        (
            "Recebido em 06/11/2025.Aprovado em 05/03/2026.",
            [
                {
                    "type": "received",
                    "day": "06",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "05",
                    "month": "03",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received July 19, 2025. Accepted for publication January 06, 2026.",
            [
                {
                    "type": "received",
                    "day": "19",
                    "month": "07",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "06",
                    "month": "01",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received: 05/08/2025Accepted: 27/03/2026Published online: 17/09/2026",
            [
                {
                    "type": "received",
                    "day": "05",
                    "month": "08",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "27",
                    "month": "03",
                    "year": "2026",
                },
                {
                    "type": "pub",
                    "day": "17",
                    "month": "09",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received: 05/08/2025. Revision requested: 20/09/2025. "
            "Revised: 29/11/2025. Accepted: 27/03/2026.",
            [
                {
                    "type": "received",
                    "day": "05",
                    "month": "08",
                    "year": "2025",
                },
                {
                    "type": "rev-request",
                    "day": "20",
                    "month": "09",
                    "year": "2025",
                },
                {
                    "type": "rev-recd",
                    "day": "29",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "27",
                    "month": "03",
                    "year": "2026",
                },
            ],
        ),
        (
            "Recebido em 05/08/2025. Revisão solicitada em 20/09/2025. "
            "Revisado em 29/11/2025. Aceito em 27/03/2026.",
            [
                {
                    "type": "received",
                    "day": "05",
                    "month": "08",
                    "year": "2025",
                },
                {
                    "type": "rev-request",
                    "day": "20",
                    "month": "09",
                    "year": "2025",
                },
                {
                    "type": "rev-recd",
                    "day": "29",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "accepted",
                    "day": "27",
                    "month": "03",
                    "year": "2026",
                },
            ],
        ),
        (
            "Received: November 6, 2025; Revised: February 10, 2026; "
            "Accepted: March 8, 2026",
            [
                {
                    "type": "received",
                    "day": "06",
                    "month": "11",
                    "year": "2025",
                },
                {
                    "type": "rev-recd",
                    "day": "10",
                    "month": "02",
                    "year": "2026",
                },
                {
                    "type": "accepted",
                    "day": "08",
                    "month": "03",
                    "year": "2026",
                },
            ],
        ),
    ],
)
def test_apply_text_fields_reads_history_dates(text, expected):
    marked = apply_text_fields({}, text)
    assert marked["history"] == expected


def test_apply_text_fields_reads_published_online_into_history_and_pub_date():
    text = "Received: 18/06/2025. Accepted: 11/12/2025. Published online: 17/09/2026."
    marked = apply_text_fields({}, text)
    assert marked["history"][-1] == {
        "type": "pub",
        "day": "17",
        "month": "09",
        "year": "2026",
    }
    xml = get_front_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    history_pub = root.find(".//history/date[@date-type='pub']")
    assert history_pub.find("day").text == "17"
    assert history_pub.find("month").text == "09"
    assert history_pub.find("year").text == "2026"
    pub = root.find(".//pub-date[@date-type='pub']")
    assert pub.find("day").text == "17"
    assert pub.find("month").text == "09"
    assert pub.find("year").text == "2026"


def test_apply_text_fields_ignores_received_in_running_text():
    text = (
        "This research received no specific grants from any funding agency.\n"
        "I received lectures in classes."
    )
    marked = apply_text_fields({}, text)
    assert "history" not in marked


def test_parse_marked_extracts_json_object_from_noise():
    marked = parse_marked('prefix {"titles":[{"kind":"main","text":"T"}]} suffix')
    assert marked == {"titles": [{"kind": "main", "text": "T"}]}


def test_parse_marked_strips_thinking_and_fenced_json():
    marked = parse_marked(
        "<think>slow reasoning</think>\n"
        '```json\n{"titles":[{"kind":"main","text":"T"}]}\n```'
    )
    assert marked == {"titles": [{"kind": "main", "text": "T"}]}


def test_parse_marked_uses_raw_decode_before_trailing_garbage():
    marked = parse_marked('{"titles":[{"kind":"main","text":"T"}]}]}]}]}')
    assert marked == {"titles": [{"kind": "main", "text": "T"}]}


def test_apply_text_fields_extracts_funding_from_heading_and_inline_grant():
    text = (
        "Funding\n"
        "This study was supported by FAPEAM under calls no. 008/2022 and no. 038/2022. "
        "CAPES process no. 303106-2025-5.\n"
        "Competing interests\n"
        "None.\n"
        "Acknowledgments\n"
        "CNPq 312345/2023-0"
    )
    marked = apply_text_fields({}, text)
    funding = marked["funding"]
    assert "FAPEAM" in funding["funding_statement"]
    sources = {item["funding_source"] for item in funding["awards"]}
    assert sources >= {"FAPEAM", "CAPES"}


def test_apply_text_fields_extracts_simple_grant_line():
    marked = apply_text_fields({}, "Title\nCNPq 312345/2023-0")
    assert marked["funding"]["awards"] == [
        {"funding_source": "CNPq", "award_id": "312345/2023-0"}
    ]


def test_apply_text_fields_reads_author_contributions_and_editorial_notes():
    text = (
        "Biota Neotropica\n"
        "Title\n"
        "Associate Editor\n"
        "Alexander Vibrans\n"
        "Author Contributions\n"
        "Karoline A. F. Ribeiro: study design; field data collection; data analysis\n"
        "Leonardo P. Reis: study design; leadership of field expeditions\n"
        "Conflicts of Interest\n"
        "The author(s) declare(s) that they have no conflict of interest.\n"
        "Ethics\n"
        "This study did not involve human beings.\n"
    )
    marked = apply_text_fields(
        {
            "authors": [
                {
                    "given_names": "Karoline A.F.",
                    "surname": "Ribeiro",
                },
                {
                    "given_names": "Leonardo P.",
                    "surname": "Reis",
                },
            ]
        },
        text,
    )
    karoline = marked["authors"][0]
    leonardo = marked["authors"][1]
    assert karoline["roles"] == [
        "study design",
        "field data collection",
        "data analysis",
    ]
    assert leonardo["roles"] == [
        "study design",
        "leadership of field expeditions",
    ]
    fns = marked["author_notes"]["fns"]
    assert fns[0] == {
        "fn_type": "edited-by",
        "label": "Associate Editor",
        "text": "Alexander Vibrans",
    }
    assert fns[1]["fn_type"] == "coi-statement"
    assert "no conflict of interest" in fns[1]["text"]
    assert fns[2]["fn_type"] == "other"
    assert fns[2]["label"] == "Ethics"


def test_get_front_xml_renders_structured_author_notes():
    xml = get_front_xml(
        {
            "titles": [{"kind": "main", "text": "Title"}],
            "author_notes": {
                "corresp": "* Corresponding author: ana@example.com",
                "fns": [
                    {
                        "fn_type": "edited-by",
                        "label": "Associate Editor",
                        "text": "Alexander Vibrans",
                    },
                    {
                        "fn_type": "coi-statement",
                        "label": "Conflicts of Interest",
                        "text": "The authors declare no conflict.",
                    },
                ],
            },
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    notes = root.find(".//author-notes")
    corresp = notes.find("corresp")
    assert corresp.get("id") == "c01"
    edited = notes.find('fn[@fn-type="edited-by"]')
    assert edited.find("label").text == "Associate Editor"
    assert edited.find("p").text == "Alexander Vibrans"
    coi = notes.find('fn[@fn-type="coi-statement"]')
    assert coi.find("label").text == "Conflicts of Interest"


def test_parse_marked_rejects_invalid_json():
    assert parse_marked("{") is None
    assert parse_marked("") is None
    assert parse_marked(None) is None
