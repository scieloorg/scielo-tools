from lxml import etree

from body.data_utils import get_body_xml, parse_marked

SPS_BODY_TAGS = {
    "body",
    "sec",
    "title",
    "p",
    "fig",
    "fig-group",
    "graphic",
    "alt-text",
    "attrib",
    "label",
    "caption",
    "table-wrap",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "table-wrap-foot",
    "fn",
    "list",
    "list-item",
    "disp-formula",
    "tex-math",
    "media",
    "supplementary-material",
    "disp-quote",
    "xref",
    "sup",
}


def test_get_body_xml_sections_fig_and_xref():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "id": "sec1",
                    "sec_type": "intro",
                    "title": "INTRODUÇÃO",
                    "content": [
                        {
                            "type": "p",
                            "text": "Texto 1 e Figura 1.",
                            "xrefs": [
                                {"ref_type": "bibr", "rid": "B1", "text": "1"},
                                {
                                    "ref_type": "fig",
                                    "rid": "f1",
                                    "text": "Figura 1",
                                },
                            ],
                        }
                    ],
                    "sections": [],
                },
                {
                    "sec_type": "results|discussion",
                    "title": "RESULTADOS E DISCUSSÃO",
                    "content": [
                        {"type": "p", "text": "Dois eixos."},
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figura 1",
                            "caption": "Sistemas da teoria.",
                            "href": "artigo-gf1.jpg",
                            "attrib": "Elaboração própria.",
                        },
                    ],
                    "sections": [
                        {
                            "title": "Eixo analítico",
                            "content": [{"type": "p", "text": "Subsecção."}],
                            "sections": [],
                        }
                    ],
                },
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag == "body"
    first, second = root.findall("sec")
    assert first.get("sec-type") == "intro"
    assert first.get("id") == "sec1"
    assert first.find("title").text == "INTRODUÇÃO"
    xref_bibr = first.find(".//xref[@ref-type='bibr']")
    assert xref_bibr.get("rid") == "B1"
    assert xref_bibr.find("sup").text == "1"
    xref_fig = first.find(".//xref[@ref-type='fig']")
    assert xref_fig.get("rid") == "f1"
    assert xref_fig.text == "Figura 1"
    assert second.get("sec-type") == "results|discussion"
    fig = second.find("fig")
    assert fig.get("id") == "f1"
    assert fig.find("label").text == "Figura 1"
    assert fig.find("caption/title").text == "Sistemas da teoria."
    nested = second.find("sec")
    assert nested.get("sec-type") is None
    assert nested.find("title").text == "Eixo analítico"
    found = {el.tag.split("}")[-1] for el in root.iter()}
    unexpected = found - SPS_BODY_TAGS
    assert not unexpected


def test_get_body_xml_table_list_and_formula():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "sec_type": "methods",
                    "title": "MÉTODO",
                    "content": [
                        {
                            "type": "list",
                            "list_type": "bullet",
                            "items": ["Item A", "Item B"],
                        },
                        {
                            "type": "table-wrap",
                            "id": "t1",
                            "label": "Tabela 1",
                            "caption": "Dados",
                            "headers": ["A", "B"],
                            "rows": [["1", "2"]],
                        },
                        {
                            "type": "disp-formula",
                            "id": "e1",
                            "label": "(1)",
                            "text": "a = b + c",
                        },
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    lst = root.find(".//list")
    assert lst.get("list-type") == "bullet"
    assert lst.find("label") is None
    wrap = root.find(".//table-wrap")
    assert wrap.get("id") == "t1"
    assert wrap.find("table/tr") is None
    assert wrap.find("table/thead/tr/th").text == "A"
    assert wrap.find("table/tbody/tr/td").text == "1"
    formula = root.find(".//disp-formula")
    assert formula.get("id") == "e1"
    assert formula.find("tex-math").text == "a = b + c"


def test_get_body_xml_omits_invalid_sec_type_and_figure_type_on_figura():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "sec_type": "not-a-type",
                    "title": "Outro título",
                    "content": [
                        {
                            "type": "fig",
                            "label": "Figura 2",
                            "fig_type": "map",
                            "caption": "Mapa",
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    sec = root.find("sec")
    assert sec.get("sec-type") is None
    fig = sec.find("fig")
    assert fig.get("id") == "f1"
    assert fig.get("fig-type") is None


def test_parse_marked_fenced_and_prose():
    marked = parse_marked(
        'Here is the JSON:\n```json\n{"sections":[{"title":"INTRODUÇÃO"}]}\n```\n'
    )
    assert marked == {"sections": [{"title": "INTRODUÇÃO"}]}


def test_parse_marked_trailing_commas():
    marked = parse_marked(
        '{"sections":[{"title":"MÉTODO","content":[{"type":"p","text":"Estudo."},],},],}'
    )
    assert marked["sections"][0]["title"] == "MÉTODO"
    assert marked["sections"][0]["content"][0]["text"] == "Estudo."


def test_parse_marked_truncated_json():
    marked = parse_marked(
        '{"sections":[{"title":"INTRODUÇÃO","content":[{"type":"p","text":"Oi"'
    )
    assert marked is None


def test_parse_marked_list_and_invalid():
    assert parse_marked('[{"title":"INTRODUÇÃO"}]') == {
        "sections": [{"title": "INTRODUÇÃO"}]
    }
    assert parse_marked("") is None
    assert parse_marked("not json at all") is None
    assert parse_marked({"sections": []}) == {"sections": []}


def test_apply_body_rules_adds_fig_table_and_cites():
    from body.utils import apply_body_rules

    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "See Figure 1 (Cardoso et al. 2017). Values in Table 1."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        },
        (
            "Introduction\n"
            "See Figure 1 (Cardoso et al. 2017). Values in Table 1.\n"
            "Figure 1. Location of the study area.\n"
            "Table 1. Species recorded."
        ),
        tables=[
            {
                "number": "1",
                "label": "Table 1",
                "caption": "Species recorded.",
                "headers": ["Family"],
                "rows": [["Arecaceae"]],
            }
        ],
    )
    intro = marked["sections"][0]
    types = [block.get("type") for block in intro["content"]]
    assert "fig" in types
    assert "table-wrap" in types
    para = intro["content"][0]
    kinds = {item["ref_type"] for item in para["xrefs"]}
    assert kinds == {"fig", "bibr", "table"}
    wrap = [block for block in intro["content"] if block.get("type") == "table-wrap"][0]
    assert wrap["headers"] == ["Family"]
    assert wrap["rows"] == [["Arecaceae"]]


def test_apply_body_rules_two_table_mentions_become_two_xrefs():
    from body.utils import apply_body_rules

    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Results",
                    "sec_type": "results",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "Highest in Transects 2 and 3 (Table 2). "
                                "Basal area ranging from 5.4 to 5.9 (Table 2)."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        },
        "Results\nHighest (Table 2). Basal (Table 2).",
    )
    texts = [
        item["text"]
        for item in marked["sections"][0]["content"][0]["xrefs"]
        if item["ref_type"] == "table"
    ]
    assert texts == ["Table 2", "Table 2"]
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    assert len(root.findall(".//xref[@ref-type='table']")) == 2


def test_apply_body_rules_marks_spruce_repeated_cites_and_particles():
    from body.utils import apply_body_rules

    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "Soils (Spruce 1871; Junk et al. 2011). "
                                "Flooding (Junk et al. 2011). "
                                "From ter Steege et al. (2013). "
                                "Following Müller-Dombois and Ellenberg (1974). "
                                "Wetlands (e.g., Junk et al., 2014). "
                                "Várzea (Wittmann et al. 2006, 2013)."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        },
        "Introduction\nSoils (Spruce 1871).",
    )
    texts = [item["text"] for item in marked["sections"][0]["content"][0]["xrefs"]]
    assert texts.count("Spruce 1871") == 1
    assert texts.count("Junk et al. 2011") == 2
    assert "ter Steege et al. (2013)" in texts
    assert "Müller-Dombois and Ellenberg (1974)" in texts
    assert "Junk et al., 2014" in texts
    assert "e.g., Junk et al., 2014" not in texts
    assert "Wittmann et al. 2006" in texts
    assert "2013" in texts


def test_apply_body_rules_inserts_fig_from_mention_and_outline():
    from body.utils import apply_body_rules

    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [
                        {"type": "p", "text": "See Figure 2 in the map."},
                    ],
                    "sections": [],
                }
            ],
            "figures": [
                {
                    "id": "f2",
                    "label": "Figure 2",
                    "caption": "Boxplots of environmental variables.",
                }
            ],
        },
        "Introduction\nSee Figure 2 in the map.",
    )
    figs = [
        block
        for block in marked["sections"][0]["content"]
        if block.get("type") == "fig"
    ]
    assert len(figs) == 1
    assert figs[0]["id"] == "f2"
    assert figs[0]["caption"] == "Boxplots of environmental variables."
    assert "figures" not in marked


def test_get_body_xml_does_not_append_unused_xrefs():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [
                        {
                            "type": "p",
                            "text": "See Figure 4.",
                            "xrefs": [
                                {
                                    "ref_type": "fig",
                                    "rid": "f4",
                                    "text": "Figure 4",
                                },
                                {
                                    "ref_type": "fig",
                                    "rid": "f4",
                                    "text": "Figure 4",
                                },
                            ],
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert len(root.findall(".//xref[@ref-type='fig']")) == 1


def test_get_body_xml_marks_repeated_needles_in_the_same_paragraph():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Results",
                    "sec_type": "results",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "Highest in Transects 2 and 3 (Table 2). "
                                "Basal area in Table 2."
                            ),
                            "xrefs": [
                                {
                                    "ref_type": "table",
                                    "rid": "t2",
                                    "text": "Table 2",
                                },
                                {
                                    "ref_type": "table",
                                    "rid": "t2",
                                    "text": "Table 2",
                                },
                            ],
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert len(root.findall(".//xref[@ref-type='table']")) == 2


def test_get_body_xml_sec_type_from_material_and_methods_title():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Material and Methods",
                    "content": [{"type": "p", "text": "A study."}],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find("sec").get("sec-type") == "materials|methods"
