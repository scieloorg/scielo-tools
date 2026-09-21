import hashlib
import json

import pytest

from reference.data_utils import get_xml
from reference.exceptions import ReferenceLlamaMisconfiguredError
from reference.models import Reference
from reference.utils.references import stz_norm


class HttpProviderStub:
    def __init__(self, *_args, **_kwargs):
        pass

    def run(self, _reference_text):
        return {
            "choices": [
                {"message": {"content": '{"reftype":"journal","title":"Remote"}'}},
            ]
        }


def test_marking_uses_http_llama(monkeypatch):
    monkeypatch.setattr(
        "reference.marking.get_provider", lambda *a, **k: HttpProviderStub()
    )

    from reference.marking import mark_reference

    result = list(mark_reference("Ref A"))

    assert result == ['{"reftype":"journal","title":"Remote"}']


def test_mark_reference_texts_batches_one_request(monkeypatch, settings):
    settings.REFERENCE_BATCH_SIZE = 10
    calls = []

    class BatchProviderStub:
        def __init__(self, messages, response_format, **_kwargs):
            self.response_format = response_format

        def run(self, text):
            calls.append(text)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "results": [
                                        {"reftype": "journal", "title": "A"},
                                        {"reftype": "journal", "title": "B"},
                                        {"reftype": "journal", "title": "C"},
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "reference.marking.get_provider",
        lambda *a, **k: BatchProviderStub(*a, **k),
    )

    from reference.marking import mark_reference_texts

    result = mark_reference_texts(["Ref A", "Ref B", "Ref C"])

    assert len(calls) == 1
    assert "1. Ref A" in calls[0]
    assert "2. Ref B" in calls[0]
    assert "3. Ref C" in calls[0]
    assert [json.loads(item)["title"] for item in result] == ["A", "B", "C"]


def test_mark_reference_texts_falls_back_on_count_mismatch(monkeypatch, settings):
    settings.REFERENCE_BATCH_SIZE = 10
    calls = []

    class MismatchThenSingleStub:
        def __init__(self, messages, response_format, **_kwargs):
            self.response_format = response_format

        def run(self, text):
            calls.append(text)
            schema = (
                self.response_format.get("schema", {}) if self.response_format else {}
            )
            if isinstance(schema.get("properties"), dict) and "results" in schema.get(
                "properties", {}
            ):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"results": [{"reftype": "journal"}]}
                                )
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"reftype": "journal", "title": text})
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "reference.marking.get_provider",
        lambda *a, **k: MismatchThenSingleStub(*a, **k),
    )

    from reference.marking import mark_reference_texts

    result = mark_reference_texts(["Ref A", "Ref B"])

    assert len(calls) == 3
    assert [json.loads(item)["title"] for item in result] == ["Ref A", "Ref B"]


def test_mark_reference_texts_single_uses_non_batch(monkeypatch, settings):
    settings.REFERENCE_BATCH_SIZE = 10
    formats = []

    class CaptureFormatStub:
        def __init__(self, messages, response_format, **_kwargs):
            formats.append(response_format)

        def run(self, _text):
            return {
                "choices": [
                    {"message": {"content": '{"reftype":"journal","title":"One"}'}}
                ]
            }

    monkeypatch.setattr(
        "reference.marking.get_provider",
        lambda *a, **k: CaptureFormatStub(*a, **k),
    )

    from reference.marking import mark_reference_texts
    from reference.prompts import RESPONSE_FORMAT

    result = mark_reference_texts(["Only one"])

    assert len(formats) == 1
    assert formats[0] is RESPONSE_FORMAT
    assert json.loads(result[0])["title"] == "One"


def test_marking_reports_llama_misconfigured(monkeypatch):
    def raise_misconfigured(*_args, **_kwargs):
        raise ReferenceLlamaMisconfiguredError("REFERENCE_URL is required.")

    monkeypatch.setattr("reference.marking.get_provider", raise_misconfigured)

    from reference.marking import mark_reference

    with pytest.raises(ReferenceLlamaMisconfiguredError, match="REFERENCE_URL"):
        list(mark_reference("Ref A"))


def test_marking_raises_llama_unavailable(monkeypatch):
    from reference.exceptions import ReferenceLlamaUnavailableError

    def raise_unavailable(*_args, **_kwargs):
        raise ReferenceLlamaUnavailableError(
            "Reference Llama service unavailable: 404 Client Error"
        )

    monkeypatch.setattr("reference.marking.get_provider", raise_unavailable)

    from reference.marking import mark_reference

    with pytest.raises(ReferenceLlamaUnavailableError, match="404"):
        list(mark_reference("Ref A"))


def test_prompt_instructs_skip_for_figures():
    from reference.prompts import (
        BATCH_RESPONSE_FORMAT,
        ITEM_PROPERTIES,
        MESSAGES,
        RESPONSE_FORMAT,
    )

    system = MESSAGES[0]["content"]
    assert "is_reference" in system
    assert "figure" in system.lower() or "Figure" in system
    assert "orcid" in system.lower()
    assert "SCIENTIFIC EDITOR" in system or "editorial" in system.lower()
    assert "Responsibility" in system or "contribution" in system.lower()
    assert "fpage" in system and "lpage" in system
    assert "do not use pages for journal page ranges" in system
    assert "Abbreviated end pages" in system
    assert "Single page" in system
    assert "whole work uses source only" in system
    assert "bare id" in system.lower() or "without https://doi.org/" in system
    assert "do not emit uri" in system
    assert "2013a" in system or "letter suffix" in system.lower()
    assert "disambiguation" in system.lower()
    assert "vol(num)" in system or "parentheses" in system.lower()
    assert ITEM_PROPERTIES["date"]["type"] == "string"
    assert RESPONSE_FORMAT["schema"].get("required") is None
    assert "results" in BATCH_RESPONSE_FORMAT["schema"]["properties"]
    assert BATCH_RESPONSE_FORMAT["schema"]["required"] == ["results"]
    for key in (
        "chapter",
        "edition",
        "fpage",
        "lpage",
        "location",
        "org_location",
        "num_pages",
        "access_id",
        "editors",
    ):
        assert key in ITEM_PROPERTIES

    pairs = list(zip(MESSAGES[1::2], MESSAGES[2::2], strict=False))
    assert len(pairs) == 7

    alvares_a = next(
        assistant["content"]
        for user, assistant in pairs
        if "2013a" in user["content"]
        and "monthly mean air temperature" in user["content"]
    )
    assert '"date":"2013a"' in alvares_a
    assert '"doi":"10.1007/s00704-012-0796-6"' in alvares_a

    journal_example = next(
        assistant["content"]
        for user, assistant in pairs
        if '"reftype":"journal"' in assistant["content"]
        and "2013b" in assistant["content"]
    )
    assert '"date":"2013b"' in journal_example
    assert '"num":6' in journal_example
    assert '"doi":"10.1127/0941-2948/2013/0507"' in journal_example
    assert '"fpage":"1751"' in journal_example
    assert '"lpage":"1752"' in journal_example
    assert '"pages"' not in journal_example
    assert "https://doi.org/" not in journal_example
    journal_user = next(
        user["content"]
        for user, assistant in pairs
        if "1751-2" in user["content"] and "2013b" in user["content"]
    )
    assert "1751-2" in journal_user

    legal_example = next(
        assistant["content"]
        for user, assistant in pairs
        if '"reftype":"legal-doc"' in assistant["content"]
    )
    assert '"collab":"Brasil"' in legal_example
    assert '"uri"' in legal_example

    batch_example = next(
        assistant["content"]
        for user, assistant in pairs
        if '"results"' in assistant["content"]
    )
    assert '"reftype":"data"' in batch_example
    assert batch_example.count('{"is_reference": false}') == 2
    batch_user = next(
        user["content"]
        for user, assistant in pairs
        if '"results"' in assistant["content"]
    )
    assert "Figure 1" in batch_user
    assert "orcid.org" in batch_user


def test_get_xml_journal():
    sample_json = json.dumps(
        {
            "reftype": "journal",
            "authors": [{"surname": "Smith", "fname": "J"}],
            "title": "Test Title",
            "source": "Nature",
            "date": "2024",
            "doi": "10.1000/test",
        }
    )
    xml_node = get_xml(sample_json)
    xml_text = json.dumps(
        {
            "tag": xml_node.tag,
            "publication_type": xml_node.get("publication-type"),
            "children": {child.tag: child.text for child in xml_node},
        }
    )
    parsed = json.loads(xml_text)

    assert parsed["tag"] == "element-citation"
    assert parsed["publication_type"] == "journal"
    assert parsed["children"]["article-title"] == "Test Title"
    assert parsed["children"]["source"] == "Nature"
    assert parsed["children"]["year"] == "2024"

    person_group = xml_node.find("person-group")
    name = person_group.find("name")
    assert name.find("surname").text == "Smith"
    assert name.find("given-names").text == "J"
    pub_id = xml_node.find("pub-id")
    assert pub_id.get("pub-id-type") == "doi"
    assert pub_id.text == "10.1000/test"


def test_extract_doi_from_text_and_enrich():
    from reference.data_utils import (
        enrich_marked_from_citation,
        extract_doi_from_text,
        extract_vol_num_from_text,
    )

    citation = (
        "Alvares, C. A. (2013a). Modeling. Theoretical and Applied Climatology, "
        "113, 407–427. https://doi.org/10.1007/s00704-012-0796-6"
    )
    assert extract_doi_from_text(citation) == "10.1007/s00704-012-0796-6"
    assert (
        extract_doi_from_text("DOI: 10.3897/zookeys.150.2109.")
        == "10.3897/zookeys.150.2109"
    )

    enriched = enrich_marked_from_citation(
        {"reftype": "journal", "title": "Modeling", "source": "TAC"},
        citation,
    )
    assert enriched["doi"] == "10.1007/s00704-012-0796-6"

    from_uri = enrich_marked_from_citation(
        {
            "reftype": "journal",
            "uri": "https://doi.org/10.1127/0941-2948/2013/0507",
        },
        "No doi label here",
    )
    assert from_uri["doi"] == "10.1127/0941-2948/2013/0507"
    assert "uri" not in from_uri

    xml_node = get_xml(json.dumps(enriched))
    assert xml_node.find("pub-id[@pub-id-type='doi']").text == (
        "10.1007/s00704-012-0796-6"
    )

    issue_citation = (
        "Alvares, C. A. (2013b). Köppen’s climate classification map for Brazil. "
        "Meteorologische Zeitschrift, 22(6), 711–728. "
        "https://doi.org/10.1127/0941-2948/2013/0507"
    )
    assert extract_vol_num_from_text(issue_citation) == {
        "vol": 22,
        "num": 6,
        "fpage": "711",
        "lpage": "728",
    }
    with_num = enrich_marked_from_citation(
        {"reftype": "journal", "title": "Köppen", "source": "MZ"},
        issue_citation,
    )
    assert with_num["vol"] == 22
    assert with_num["num"] == 6
    assert with_num["fpage"] == "711"
    assert with_num["lpage"] == "728"
    assert with_num["doi"] == "10.1127/0941-2948/2013/0507"
    num_xml = get_xml(json.dumps(with_num))
    assert num_xml.find("volume").text == "22"
    assert num_xml.find("issue").text == "6"
    assert num_xml.find("fpage").text == "711"
    assert num_xml.find("lpage").text == "728"

    from reference.data_utils import extract_uri_from_text

    cran = (
        "Augie, B. (2017). gridExtra: Miscellaneous functions for “Grid” graphics "
        "(Version 2.3) [R package]. https://CRAN.R-project.org/package=gridExtra"
    )
    assert extract_uri_from_text(cran) == "https://CRAN.R-project.org/package=gridExtra"
    with_uri = enrich_marked_from_citation(
        {"reftype": "software", "source": "gridExtra", "version": "2.3"},
        cran,
    )
    assert with_uri["uri"] == "https://CRAN.R-project.org/package=gridExtra"
    uri_xml = get_xml(json.dumps(with_uri))
    assert uri_xml.find("ext-link").text == (
        "https://CRAN.R-project.org/package=gridExtra"
    )

    web_doi = (
        "Brasil. (2024). Decreto. http://dx.doi.org/10.18542/ethnoscientia.v0i0.10245"
    )
    web_enriched = enrich_marked_from_citation(
        {"reftype": "webpage", "source": "Decreto"},
        web_doi,
    )
    assert web_enriched["uri"] == "http://dx.doi.org/10.18542/ethnoscientia.v0i0.10245"
    assert "doi" not in web_enriched or web_enriched.get("doi") in (None, "")


def test_get_xml_book():
    sample_json = json.dumps(
        {
            "reftype": "book",
            "title": "Tropical soil biology",
            "organization": "CAB International",
            "date": 1993,
        }
    )
    xml_node = get_xml(sample_json)
    assert xml_node.get("publication-type") == "book"
    assert xml_node.find("source").text == "Tropical soil biology"
    assert xml_node.find("publisher-name").text == "CAB International"
    assert xml_node.find("year").text == "1993"


def test_get_xml_book_chapter_uses_part_title():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "book",
                "chapter_title": "Mapping wetlands",
                "source": "IGARSS proceedings",
                "date": 2003,
                "pages": "1375-1377",
            }
        )
    )
    assert xml_node.find("part-title").text == "Mapping wetlands"
    assert xml_node.find("chapter-title") is None
    assert xml_node.find("source").text == "IGARSS proceedings"
    assert xml_node.find("fpage").text == "1375"
    assert xml_node.find("lpage").text == "1377"


def test_get_xml_book_chapter_field_and_editors():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "book",
                "chapter": "The epidemiology of idiopathic inflammatory bowel disease",
                "source": "Inflammatory bowel disease",
                "edition": "4th",
                "editors": [{"surname": "Kirsner", "fname": "JB"}],
                "organization": "Williams & Wilkins",
                "location": "Baltimore",
                "fpage": "31",
                "lpage": "68",
                "date": 1995,
            }
        )
    )
    assert xml_node.find("part-title").text.startswith("The epidemiology")
    assert xml_node.find("edition").text == "4th"
    assert xml_node.find("publisher-loc").text == "Baltimore"
    assert xml_node.find("fpage").text == "31"
    assert xml_node.find("lpage").text == "68"
    editors = xml_node.find('person-group[@person-group-type="editor"]')
    assert editors.find("name/surname").text == "Kirsner"


def test_get_xml_journal_pages_and_elocation():
    ranged = get_xml(
        json.dumps(
            {
                "reftype": "journal",
                "title": "A",
                "source": "B",
                "pages": "117-126",
            }
        )
    )
    assert ranged.find("fpage").text == "117"
    assert ranged.find("lpage").text == "126"

    explicit = get_xml(
        json.dumps(
            {
                "reftype": "journal",
                "title": "A",
                "source": "B",
                "fpage": "117",
                "lpage": "126",
                "doi": "https://doi.org/10.3897/zookeys.150.2109",
            }
        )
    )
    assert explicit.find("fpage").text == "117"
    assert explicit.find("lpage").text == "126"
    assert explicit.find("pub-id").text == "10.3897/zookeys.150.2109"

    single = get_xml(
        json.dumps(
            {
                "reftype": "journal",
                "title": "A",
                "source": "B",
                "pages": "244",
            }
        )
    )
    assert single.find("fpage").text == "244"
    assert single.find("lpage") is None

    elocation = get_xml(
        json.dumps(
            {
                "reftype": "journal",
                "title": "A",
                "source": "B",
                "pages": "e240058",
            }
        )
    )
    assert elocation.find("elocation-id").text == "e240058"
    assert elocation.find("fpage") is None


def test_get_xml_thesis_source_location_num_pages():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "thesis",
                "source": "Sur le genre Phyllanthus L.",
                "degree": "doctorat",
                "organization": "l’Université L. Pasteur",
                "location": "Strasbourg, France",
                "num_pages": 760,
                "date": 1987,
            }
        )
    )
    assert xml_node.find("source").text == "Sur le genre Phyllanthus L."
    assert xml_node.find("publisher-loc").text == "Strasbourg, France"
    size = xml_node.find("size")
    assert size.get("units") == "pages"
    assert size.text == "760"


def test_get_xml_data_uses_data_title():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "data",
                "title": "Replication data for X",
                "source": "SciELO Data",
                "doi": "10.48331/scielodata.abc",
                "date": 2025,
            }
        )
    )
    assert xml_node.get("publication-type") == "data"
    assert xml_node.find("data-title").text == "Replication data for X"
    assert xml_node.find("source").text == "SciELO Data"


def test_get_xml_software():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "software",
                "title": "R: A language and environment",
                "organization": "R Foundation",
                "uri": "https://www.R-project.org/",
                "date": 2021,
            }
        )
    )
    assert xml_node.get("publication-type") == "software"
    assert xml_node.find("source").text == "R: A language and environment"
    assert xml_node.find("ext-link").text == "https://www.R-project.org/"


def test_get_xml_missing_reftype_returns_error():
    xml_node = get_xml(json.dumps({"title": "No type"}))
    assert xml_node.tag == "error"


def test_build_ref_list():
    from lxml import etree

    from reference.data_utils import build_ref_list

    results = [
        {
            "mixed_citation": "Smith J. Nature. 2024.",
            "data": (
                '<element-citation publication-type="journal">'
                "<article-title>Nature paper</article-title>"
                '<pub-id pub-id-type="doi">10.1/abc</pub-id>'
                "</element-citation>"
            ),
        },
        {
            "mixed_citation": "Doe A. Book title. Publisher.",
            "data": (
                '<element-citation publication-type="book">'
                "<source>Book title</source>"
                "</element-citation>"
            ),
        },
    ]
    xml_text = build_ref_list(results)
    root = etree.fromstring(xml_text.encode("utf-8"))

    assert root.tag == "ref-list"
    assert root.find("title").text == "References"
    refs = root.findall("ref")
    assert len(refs) == 2
    assert refs[0].get("id") == "B1"
    assert refs[1].get("id") == "B2"
    assert refs[0].find("mixed-citation").text == "Smith J. Nature. 2024."
    assert refs[0].find("element-citation").get("publication-type") == "journal"
    assert refs[0].find("element-citation/pub-id").text == "10.1/abc"
    assert refs[1].find("element-citation").get("publication-type") == "book"


def test_build_ref_list_skips_error_element_citation():
    from lxml import etree

    from reference.data_utils import build_ref_list

    xml_text = build_ref_list(
        [
            {
                "mixed_citation": "Broken ref",
                "data": "<error/>",
            }
        ]
    )
    root = etree.fromstring(xml_text.encode("utf-8"))
    ref = root.find("ref")
    assert ref.find("mixed-citation").text == "Broken ref"
    assert ref.find("element-citation") is None


@pytest.mark.django_db
def test_stz_norm_checksum():
    citation = "Smith J.  Nature.  2024."
    reference = Reference(mixed_citation=citation)
    reference.save()

    expected_normalized = stz_norm(citation)
    expected_checksum = hashlib.sha256(expected_normalized.encode("utf-8")).hexdigest()

    assert reference.normalized_citation == expected_normalized
    assert reference.checksum == expected_checksum
