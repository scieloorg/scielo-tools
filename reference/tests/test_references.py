import json
import re

import pytest
from lxml import etree

from reference.data_utils import build_ref_list, get_xml
from reference.fixtures.references import REF_LIST_XML, REFERENCES
from reference.marking import mark_reference


def _collapse_ws(value):
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def _golden_element_citations():
    root = etree.fromstring(REF_LIST_XML.encode("utf-8"))
    return [ref.find("element-citation") for ref in root.findall("ref")]


def _fields_from_element_citation(node):
    if node is None:
        return {}
    fields = {
        "reftype": node.get("publication-type"),
        "date": _collapse_ws(node.findtext("year")),
        "doi": _collapse_ws(node.findtext("pub-id[@pub-id-type='doi']")),
        "vol": _collapse_ws(node.findtext("volume")),
        "num": _collapse_ws(node.findtext("issue")),
        "title": _collapse_ws(
            node.findtext("article-title")
            or node.findtext("part-title")
            or node.findtext("data-title")
            or node.findtext("conf-name")
            or node.findtext("source")
        ),
        "source": _collapse_ws(node.findtext("source")),
    }
    fpage = _collapse_ws(node.findtext("fpage"))
    lpage = _collapse_ws(node.findtext("lpage"))
    elocation = _collapse_ws(node.findtext("elocation-id"))
    if fpage and lpage:
        fields["pages"] = f"{fpage}-{lpage}"
    elif fpage:
        fields["pages"] = fpage
    elif elocation:
        fields["pages"] = elocation
    else:
        fields["pages"] = None
    uri_nodes = node.xpath(".//ext-link")
    fields["uri"] = _collapse_ws(uri_nodes[0].text) if uri_nodes else None
    authors = []
    person_group = node.find("person-group[@person-group-type='author']")
    if person_group is not None:
        for child in person_group:
            if child.tag == "collab":
                authors.append({"collab": _collapse_ws(child.text)})
            elif child.tag == "name":
                authors.append(
                    {
                        "surname": _collapse_ws(child.findtext("surname")),
                        "fname": _collapse_ws(child.findtext("given-names")),
                    }
                )
    fields["authors"] = authors
    return fields


def _fields_from_marked_json(data):
    pages = data.get("pages")
    if pages is not None:
        pages = _collapse_ws(str(pages).replace("–", "-").replace("—", "-"))
    authors = []
    for author in data.get("authors") or []:
        if (
            author.get("collab")
            and not author.get("surname")
            and not author.get("fname")
        ):
            authors.append({"collab": _collapse_ws(author.get("collab"))})
        else:
            authors.append(
                {
                    "surname": _collapse_ws(author.get("surname")),
                    "fname": _collapse_ws(author.get("fname")),
                }
            )
    title = data.get("title") or data.get("chapter_title") or data.get("source")
    return {
        "reftype": data.get("reftype"),
        "date": _collapse_ws(data.get("date")),
        "doi": _collapse_ws(data.get("doi")),
        "vol": _collapse_ws(data.get("vol")),
        "num": _collapse_ws(data.get("num")),
        "pages": pages,
        "title": _collapse_ws(title),
        "source": _collapse_ws(data.get("source")),
        "uri": _collapse_ws(data.get("uri")),
        "authors": authors,
    }


def _comparable_keys(expected_fields):
    keys = ["reftype", "date", "doi", "vol", "num", "pages", "title", "source", "uri"]
    return [key for key in keys if expected_fields.get(key) not in (None, "")]


def _assert_marked_matches_golden(marked, golden_node, ref_id):
    expected = _fields_from_element_citation(golden_node)
    actual = _fields_from_marked_json(marked)
    for key in _comparable_keys(expected):
        assert actual.get(key) == expected.get(key), (
            f"{ref_id} field {key}: expected {expected.get(key)!r}, "
            f"got {actual.get(key)!r}"
        )
    if expected["authors"]:
        assert len(actual["authors"]) >= min(3, len(expected["authors"])), (
            f"{ref_id} authors count: expected at least "
            f"{min(3, len(expected['authors']))}, got {len(actual['authors'])}"
        )
        for index, expected_author in enumerate(
            expected["authors"][: min(3, len(expected["authors"]))]
        ):
            actual_author = actual["authors"][index]
            for field_name, expected_value in expected_author.items():
                if expected_value in (None, ""):
                    continue
                assert _collapse_ws(actual_author.get(field_name)) == expected_value, (
                    f"{ref_id} author[{index}].{field_name}: "
                    f"expected {expected_value!r}, "
                    f"got {actual_author.get(field_name)!r}"
                )


def _assert_element_citation_matches(actual_node, golden_node, ref_id):
    expected = _fields_from_element_citation(golden_node)
    actual = _fields_from_element_citation(actual_node)
    for key in _comparable_keys(expected):
        assert actual.get(key) == expected.get(key), (
            f"{ref_id} JATS field {key}: expected {expected.get(key)!r}, "
            f"got {actual.get(key)!r}"
        )


def _mark_eval_reference(index):
    ref_id = f"B{index + 1}"
    citation = REFERENCES[index]
    choices = list(mark_reference(citation))
    assert choices, f"{ref_id}: Llama returned no choices"
    raw = choices[0]
    assert "Llama model is not available" not in raw, f"{ref_id}: {raw}"
    assert "unexpected error" not in raw.lower(), f"{ref_id}: {raw}"
    try:
        marked = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{ref_id}: invalid JSON from Llama: {raw!r}") from exc
    assert marked.get("reftype"), f"{ref_id}: missing reftype in {marked!r}"
    return marked, raw


@pytest.fixture(scope="module")
def eval_llama_marked():
    return [_mark_eval_reference(index) for index in range(len(REFERENCES))]


def test_eval_corpus_aligned():
    golden_nodes = _golden_element_citations()
    assert len(REFERENCES) == len(golden_nodes)
    assert len(REFERENCES) == 103
    assert all(node is not None for node in golden_nodes)


@pytest.mark.llama
def test_eval_llama_json_matches_golden(eval_llama_marked):
    golden_nodes = _golden_element_citations()
    for index, golden_node in enumerate(golden_nodes):
        marked, _raw = eval_llama_marked[index]
        _assert_marked_matches_golden(marked, golden_node, f"B{index + 1}")


@pytest.mark.llama
def test_eval_llama_jats_matches_golden(eval_llama_marked):
    golden_nodes = _golden_element_citations()
    results = []
    for index, golden_node in enumerate(golden_nodes):
        marked, raw = eval_llama_marked[index]
        xml_node = get_xml(raw)
        assert xml_node.tag != "error", (
            f"B{index + 1}: get_xml returned error for {marked!r}"
        )
        _assert_element_citation_matches(xml_node, golden_node, f"B{index + 1}")
        results.append(
            {
                "mixed_citation": REFERENCES[index],
                "data": etree.tostring(xml_node, encoding="unicode"),
            }
        )

    built = build_ref_list(results)
    built_root = etree.fromstring(
        built.replace(
            "<ref-list>",
            '<ref-list xmlns:xlink="http://www.w3.org/1999/xlink">',
            1,
        ).encode("utf-8")
    )
    built_nodes = [ref.find("element-citation") for ref in built_root.findall("ref")]
    assert len(built_nodes) == len(golden_nodes)
    pairs = zip(built_nodes, golden_nodes, strict=True)
    for index, (built_node, golden_node) in enumerate(pairs):
        _assert_element_citation_matches(built_node, golden_node, f"B{index + 1}")
