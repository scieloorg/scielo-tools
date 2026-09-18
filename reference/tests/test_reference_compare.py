import sys
from pathlib import Path

from lxml import etree

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from reference_compare import (
    compare_element_citations,
    doi_from_uri_value,
    fields_from_element_citation,
    normalize_pages_value,
    normalize_year_value,
    sps_normalize_fields,
)


def _element(xml):
    return etree.fromstring(xml)


def test_doi_from_uri_value_accepts_doi_urls_and_bare():
    assert (
        doi_from_uri_value("https://doi.org/10.1590/S0101-81752008000400022")
        == "10.1590/S0101-81752008000400022"
    )
    assert (
        doi_from_uri_value("http://dx.doi.org/10.18542/ethnoscientia.v0i0.10245")
        == "10.18542/ethnoscientia.v0i0.10245"
    )
    assert doi_from_uri_value("10.1097/PEC.0b013e31827b5733") == (
        "10.1097/PEC.0b013e31827b5733"
    )
    assert doi_from_uri_value("https://agromet.cpact.embrapa.br/boletim/") is None


def test_sps_normalize_fields_promotes_doi_uri_to_doi():
    fields = sps_normalize_fields(
        {
            "doi": None,
            "uri": "https://doi.org/10.11646/zootaxa.4712.1.1",
        }
    )
    assert fields["doi"] == "10.11646/zootaxa.4712.1.1"
    assert fields["uri"] is None


def test_sps_normalize_fields_keeps_generic_uri():
    fields = sps_normalize_fields(
        {
            "doi": None,
            "uri": "https://agromet.cpact.embrapa.br/boletim/",
        }
    )
    assert fields["doi"] is None
    assert fields["uri"] == "https://agromet.cpact.embrapa.br/boletim/"


def test_compare_doi_ignores_case():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Title</article-title>
          <source>Source</source>
          <pub-id pub-id-type="doi">10.1590/0103-11042020e204</pub-id>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Title</article-title>
          <source>Source</source>
          <pub-id pub-id-type="doi">10.1590/0103-11042020E204</pub-id>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "doi" for item in result["mismatches"])


def test_compare_doi_ext_link_golden_matches_pub_id_predicted():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Title</article-title>
          <source>ZooKeys</source>
          <year>2011</year>
          <ext-link ext-link-type="uri"
            >https://doi.org/10.3897/zookeys.150.2109</ext-link>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Title</article-title>
          <source>ZooKeys</source>
          <year>2011</year>
          <pub-id pub-id-type="doi">10.3897/zookeys.150.2109</pub-id>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert "uri" not in result["comparable_keys"]
    assert "doi" in result["comparable_keys"]
    assert result["expected"]["doi"] == "10.3897/zookeys.150.2109"
    assert result["actual"]["doi"] == "10.3897/zookeys.150.2109"
    assert not any(item["field"] == "uri" for item in result["mismatches"])
    assert not any(item["field"] == "doi" for item in result["mismatches"])


def test_fields_from_element_citation_clears_doi_uri():
    node = _element(
        """
        <element-citation publication-type="journal">
          <ext-link ext-link-type="uri"
            >https://doi.org/10.1590/S0101-81752008000400022</ext-link>
        </element-citation>
        """
    )
    fields = fields_from_element_citation(node)
    assert fields["doi"] == "10.1590/S0101-81752008000400022"
    assert fields["uri"] is None


def test_normalize_pages_value_expands_abbreviated_end():
    assert normalize_pages_value("1751-2") == "1751-1752"
    assert normalize_pages_value("1105-10") == "1105-1110"
    assert normalize_pages_value("83-9") == "83-89"
    assert normalize_pages_value("307-19") == "307-319"
    assert normalize_pages_value("1751-1752") == "1751-1752"
    assert normalize_pages_value("307-319") == "307-319"


def test_normalize_pages_value_collapses_duplicate_single_page():
    assert normalize_pages_value("237-237") == "237"
    assert normalize_pages_value("237") == "237"
    assert normalize_pages_value("e20250312-e20250312") == "e20250312"


def test_normalize_pages_value_keeps_distinct_ranges():
    assert normalize_pages_value("1093-1095") == "1093-1095"
    assert normalize_pages_value("1093-1105") == "1093-1105"
    assert normalize_pages_value("1093-1095") != normalize_pages_value("1093-1105")


def test_normalize_year_value_strips_disambiguation_letter():
    assert normalize_year_value("2019a") == "2019"
    assert normalize_year_value("2019b") == "2019"
    assert normalize_year_value("2013A") == "2013"
    assert normalize_year_value("2019") == "2019"
    assert normalize_year_value("n.d.") == "n.d."
    assert normalize_year_value(None) is None
    assert normalize_year_value("") is None


def test_compare_date_letter_suffix_matches_plain_year():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <year>2019b</year>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <year>2019</year>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "date" for item in result["mismatches"])


def test_compare_date_distinct_years_still_mismatch():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <year>2019a</year>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <year>2018</year>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert any(item["field"] == "date" for item in result["mismatches"])


def test_compare_pages_abbreviated_matches_full():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <fpage>1751</fpage>
          <lpage>1752</lpage>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <fpage>1751</fpage>
          <lpage>2</lpage>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "pages" for item in result["mismatches"])


def test_compare_pages_single_matches_duplicated_range():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <fpage>237</fpage>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <fpage>237</fpage>
          <lpage>237</lpage>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "pages" for item in result["mismatches"])


def test_compare_pages_distinct_ranges_still_mismatch():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <fpage>1093</fpage>
          <lpage>1095</lpage>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <fpage>1093</fpage>
          <lpage>1105</lpage>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    pages_mismatches = [
        item for item in result["mismatches"] if item["field"] == "pages"
    ]
    assert len(pages_mismatches) == 1
    assert pages_mismatches[0]["expected"] == "1093-1095"
    assert pages_mismatches[0]["actual"] == "1093-1105"


def test_compare_title_source_close_by_proximity():
    expected = _element(
        """
        <element-citation publication-type="book">
          <part-title>Chapter</part-title>
          <source>Amazonian floodplain forests: Ecophysiology, biodiversity
            and sustainable management (pp. 355–372)</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="book">
          <part-title>Chapter</part-title>
          <source>Amazonian floodplain forests: Ecophysiology, biodiversity
            and sustainable management</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "source" for item in result["mismatches"])
    assert not any(item["field"] == "title" for item in result["mismatches"])


def test_compare_title_hyphen_vs_concat_close_by_proximity():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Estrutura, composição florística e etnobiologia de um
            buritizal na fronteira biológica Amazônia-Cerrado</article-title>
          <source>Journal</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Estrutura, composição florística e etnobiologia de um
            buritizal na fronteira biológica AmazôniaCerrado</article-title>
          <source>Journal</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert not any(item["field"] == "title" for item in result["mismatches"])


def test_compare_title_distinct_still_mismatch():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Modeling monthly mean air temperature for Brazil</article-title>
          <source>Theoretical and Applied Climatology</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <article-title>Os domínios da natureza no Brasil: Potencialidades
            paisagísticas</article-title>
          <source>Ateliê Editorial</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=False)
    assert any(item["field"] == "title" for item in result["mismatches"])
    assert any(item["field"] == "source" for item in result["mismatches"])


def test_compare_authors_surname_close_by_proximity():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name>
              <surname>CARVALHO-BRITO</surname>
              <given-names>V</given-names>
            </name>
          </person-group>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name>
              <surname>CarvalhoBrito</surname>
              <given-names>V</given-names>
            </name>
          </person-group>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=True)
    assert not any(
        str(item["field"]).startswith("authors") for item in result["mismatches"]
    )


def test_compare_authors_surname_distinct_still_mismatch():
    expected = _element(
        """
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name>
              <surname>SILVA</surname>
              <given-names>A</given-names>
            </name>
          </person-group>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    actual = _element(
        """
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name>
              <surname>SANTOS</surname>
              <given-names>A</given-names>
            </name>
          </person-group>
          <article-title>Title</article-title>
          <source>Source</source>
        </element-citation>
        """
    )
    result = compare_element_citations(actual, expected, check_authors=True)
    assert any(item["field"] == "authors[0].surname" for item in result["mismatches"])
