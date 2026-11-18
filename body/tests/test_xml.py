from lxml import etree

from body.data_utils import get_body_xml, parse_marked, promote_encoded_formulas
from body.utils import FORMULA_MARK, expand_encoded_formulas

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
    graphic = fig.find("graphic")
    assert graphic is not None
    assert graphic.get("id") == "g1"
    assert graphic.get("{http://www.w3.org/1999/xlink}href") == "artigo-gf1.jpg"
    nested = second.find("sec")
    assert nested.get("sec-type") is None
    assert nested.find("title").text == "Eixo analítico"
    found = {el.tag.split("}")[-1] for el in root.iter()}
    unexpected = found - SPS_BODY_TAGS
    assert not unexpected


def test_get_body_xml_assigns_sequential_graphic_ids():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Results",
                    "sec_type": "results",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "href": "fig-1.jpg",
                        },
                        {
                            "type": "fig",
                            "id": "f2",
                            "label": "Figure 2",
                            "href": "fig-2.jpg",
                        },
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    ids = [el.get("id") for el in root.findall(".//graphic")]
    hrefs = [
        el.get("{http://www.w3.org/1999/xlink}href")
        for el in root.findall(".//graphic")
    ]
    assert ids == ["g1", "g2"]
    assert hrefs == ["fig-1.jpg", "fig-2.jpg"]


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
    graphic = fig.find("graphic")
    assert graphic is not None
    assert graphic.get("{http://www.w3.org/1999/xlink}href") == "fig-1.jpg"


def test_get_body_xml_infers_data_availability_specific_use():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Data Availability",
                    "sec_type": "data-availability",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "Datasets are available upon request from the "
                                "corresponding author."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    sec = root.find("sec")
    assert sec.get("sec-type") == "data-availability"
    assert sec.get("specific-use") == "data-available-upon-request"


def test_get_body_xml_infers_data_in_article_from_within_the_article():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Data availability",
                    "sec_type": "data-availability",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "All data that support the findings of this study "
                                "are included within the article."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find("sec").get("specific-use") == "data-in-article"


def test_get_body_xml_defaults_data_availability_to_uninformed():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Data Availability",
                    "sec_type": "data-availability",
                    "content": [{"type": "p", "text": "See the authors."}],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    sec = root.find("sec")
    assert sec.get("specific-use") == "uninformed"


def test_get_body_xml_renders_ack():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Acknowledgments",
                    "sec_type": "acknowledgments",
                    "content": [{"type": "p", "text": "Thanks to CNPq."}],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    ack = root.find("ack")
    assert ack is not None
    assert ack.find("title").text == "Acknowledgments"
    assert ack.find("p").text == "Thanks to CNPq."
    assert root.find("sec") is None


def test_get_body_xml_supplementary_material_uses_plain_paragraphs():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "title": "Supplementary Material",
                    "sec_type": "supplementary-material",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "Figure S1 – Schematic representation of "
                                "the study area."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    sec = root.find("sec")
    assert sec.get("sec-type") == "supplementary-material"
    assert sec.find("p").text.startswith("Figure S1")
    assert sec.find(".//inline-supplementary-material") is None


def test_get_body_xml_places_supplementary_material_after_tail_sections():
    xml = get_body_xml(
        {
            "sections": [
                {
                    "sec_type": "conclusions",
                    "title": "Conclusions",
                    "content": [{"type": "p", "text": "Done."}],
                    "sections": [],
                },
                {
                    "title": "Supplementary Material",
                    "sec_type": "supplementary-material",
                    "content": [{"type": "p", "text": "Figure S1."}],
                    "sections": [],
                },
                {
                    "title": "Acknowledgments",
                    "sec_type": "acknowledgments",
                    "content": [{"type": "p", "text": "Thanks."}],
                    "sections": [],
                },
                {
                    "title": "Data Availability",
                    "sec_type": "data-availability",
                    "specific_use": "data-available-upon-request",
                    "content": [{"type": "p", "text": "Upon request."}],
                    "sections": [],
                },
            ]
        }
    )
    root = etree.fromstring(xml.encode("utf-8"))
    children = list(root)
    assert children[0].tag == "sec"
    assert children[0].get("sec-type") == "conclusions"
    assert children[1].tag == "ack"
    assert children[2].tag == "sec"
    assert children[2].get("sec-type") == "data-availability"
    assert children[3].tag == "sec"
    assert children[3].get("sec-type") == "supplementary-material"
    body_secs = root.findall("sec")
    assert body_secs[-1].get("sec-type") == "supplementary-material"


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


def test_apply_body_rules_places_spanish_tabla_with_fuente():
    from body.utils import apply_body_rules

    source = "\n".join(
        [
            "Introducción",
            "El portal presenta una usabilidad óptima (ver tabla 1).",
            "Tabla 1. Confianza en shopDisney.es, dimensión Diseño y Navegación",
            "Fuente: elaboración propia.",
        ]
    )
    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Introducción",
                    "sec_type": "intro",
                    "content": [
                        {
                            "type": "p",
                            "text": (
                                "El portal presenta una usabilidad óptima "
                                "(ver tabla 1)."
                            ),
                        }
                    ],
                    "sections": [],
                }
            ]
        },
        source,
        tables=[
            {
                "number": "1",
                "label": "Tabla 1",
                "caption": (
                    "Confianza en shopDisney.es, dimensión Diseño y Navegación"
                ),
                "headers": ["Indicadores", "Sí", "No"],
                "rows": [["Protocolo seguro", "https", ""]],
            }
        ],
    )
    content = marked["sections"][0]["content"]
    xref = content[0]["xrefs"][0]
    assert xref["ref_type"] == "table"
    assert xref["rid"] == "t1"
    assert xref["text"] == "tabla 1"
    wrap = content[1]
    assert wrap["type"] == "table-wrap"
    assert wrap["label"] == "Tabla 1"
    assert (
        wrap["caption"] == "Confianza en shopDisney.es, dimensión Diseño y Navegación"
    )
    assert wrap["attrib"] == "elaboración propia."
    assert wrap["headers"] == ["Indicadores", "Sí", "No"]
    assert wrap["rows"] == [["Protocolo seguro", "https", ""]]
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    label = root.find(".//table-wrap/label")
    attrib = root.find(".//table-wrap/attrib")
    assert label.text == "Tabla 1"
    assert attrib.text == "elaboración propia."
    assert root.find(".//xref[@ref-type='table']").get("rid") == "t1"


def test_apply_body_rules_puts_table_wrap_where_the_label_is():
    from body.utils import apply_body_rules

    source = "\n".join(
        [
            "Metodología",
            "Texto antes da tabela.",
            "Tabla 1. Confianza en shopDisney.es, dimensión Diseño y Navegación",
            "Fuente: elaboración propia.",
            "Texto depois da tabela.",
        ]
    )
    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Metodología",
                    "sec_type": "methods",
                    "content": [
                        {"type": "p", "text": "Texto antes da tabela."},
                        {
                            "type": "p",
                            "text": (
                                "Tabla 1. Confianza en shopDisney.es, "
                                "dimensión Diseño y Navegación"
                            ),
                        },
                        {"type": "p", "text": "Fuente: elaboración propia."},
                        {"type": "p", "text": "Texto depois da tabela."},
                        {
                            "type": "table-wrap",
                            "id": "t1",
                            "label": "Table 1",
                            "caption": "",
                            "headers": ["Indicadores", "Sí", "No"],
                            "rows": [["Protocolo seguro", "https", ""]],
                        },
                    ],
                    "sections": [],
                }
            ]
        },
        source,
        tables=[
            {
                "number": "1",
                "label": "Tabla 1",
                "caption": (
                    "Confianza en shopDisney.es, dimensión Diseño y Navegación"
                ),
                "headers": ["Indicadores", "Sí", "No"],
                "rows": [["Protocolo seguro", "https", ""]],
            }
        ],
    )
    content = marked["sections"][0]["content"]
    assert [block["type"] for block in content] == ["p", "table-wrap", "p"]
    assert content[0]["text"] == "Texto antes da tabela."
    assert content[2]["text"] == "Texto depois da tabela."
    wrap = content[1]
    assert wrap["id"] == "t1"
    assert wrap["label"] == "Tabla 1"
    assert (
        wrap["caption"] == "Confianza en shopDisney.es, dimensión Diseño y Navegación"
    )
    assert wrap["attrib"] == "elaboración propia."
    assert wrap["headers"] == ["Indicadores", "Sí", "No"]
    assert wrap["rows"] == [["Protocolo seguro", "https", ""]]


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
                    "href": "fig-2.jpg",
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
    assert figs[0]["href"] == "fig-2.jpg"
    assert "figures" not in marked


def test_apply_body_rules_fills_href_on_existing_fig():
    from body.utils import apply_body_rules

    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [
                        {"type": "p", "text": "See Figure 1."},
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Existing caption.",
                        },
                    ],
                    "sections": [],
                }
            ],
            "figures": [
                {
                    "id": "f1",
                    "label": "Figure 1",
                    "href": "fig-1.jpg",
                }
            ],
        },
        "Introduction\nSee Figure 1.",
    )
    figs = [
        block
        for block in marked["sections"][0]["content"]
        if block.get("type") == "fig"
    ]
    assert len(figs) == 1
    assert figs[0]["href"] == "fig-1.jpg"
    assert figs[0]["caption"] == "Existing caption."


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


def test_encoded_formula_paragraph_becomes_mathml():
    math = (
        '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" id="m1">'
        "<mml:mi>a</mml:mi></mml:math>"
    )
    line = f"{FORMULA_MARK}d{FORMULA_MARK}e1{FORMULA_MARK}(1){FORMULA_MARK}{math}"
    inline = (
        f"that is, {FORMULA_MARK}i{FORMULA_MARK}e4{FORMULA_MARK}{math}{FORMULA_MARK}."
    )
    marked = expand_encoded_formulas(
        {
            "sections": [
                {
                    "title": "Results",
                    "content": [
                        {"type": "p", "text": line},
                        {"type": "p", "text": inline},
                    ],
                }
            ]
        }
    )
    content = marked["sections"][0]["content"]
    assert content[0]["type"] == "disp-formula"
    assert content[0]["id"] == "e1"
    assert content[0]["label"] == "(1)"
    assert content[1]["formulas"][0]["id"] == "e4"
    assert content[1]["text"] == f"that is, {FORMULA_MARK}e4{FORMULA_MARK}."
    assert "mml:math" not in content[1]["text"]
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(".//disp-formula").get("id") == "e1"
    assert root.find(".//disp-formula/label").text == "(1)"
    assert root.find(".//{http://www.w3.org/1998/Math/MathML}mi").text == "a"
    assert root.find(".//inline-formula").get("id") == "e4"
    assert FORMULA_MARK not in xml
    stored = (
        "<body><sec><title>Results</title>"
        f"<p>{line.replace('<', '&lt;').replace('>', '&gt;')}</p>"
        "</sec></body>"
    )
    repaired = promote_encoded_formulas(etree.fromstring(stored.encode("utf-8")))
    formula = repaired.find(".//disp-formula")
    assert formula.get("id") == "e1"
    assert formula.find(".//{http://www.w3.org/1998/Math/MathML}mi").text == "a"
    assert repaired.find(".//p") is None


def test_promote_keeps_less_than_operator_in_second_formula():
    math = etree.Element("{http://www.w3.org/1998/Math/MathML}math")
    math.set("id", "m2")
    mo = etree.SubElement(math, "{http://www.w3.org/1998/Math/MathML}mo")
    mo.text = "<"
    payload = etree.tostring(math, encoding="unicode")
    line = f"{FORMULA_MARK}d{FORMULA_MARK}e2{FORMULA_MARK}(2){FORMULA_MARK}{payload}"
    body = etree.Element("body")
    paragraph = etree.SubElement(body, "p")
    paragraph.text = line
    repaired = promote_encoded_formulas(
        etree.fromstring(etree.tostring(body, encoding="unicode").encode("utf-8"))
    )
    formula = repaired.find("disp-formula")
    assert formula.get("id") == "e2"
    assert formula.find("tex-math") is None
    assert formula.find(".//{http://www.w3.org/1998/Math/MathML}mo").text == "<"
    broken = etree.Element("disp-formula")
    broken.set("id", "e2")
    tex = etree.SubElement(broken, "tex-math")
    tex.text = payload.replace("&lt;", "<")
    host = etree.Element("body")
    host.append(broken)
    fixed = promote_encoded_formulas(
        etree.fromstring(etree.tostring(host, encoding="unicode").encode("utf-8"))
    )
    assert fixed.find(".//tex-math") is None
    assert fixed.find(".//{http://www.w3.org/1998/Math/MathML}mo").text == "<"


def test_promote_inline_formula_after_xref():
    math = (
        '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" id="m5">'
        "<mml:mi>e</mml:mi></mml:math>"
    )
    token = f"{FORMULA_MARK}i{FORMULA_MARK}e5{FORMULA_MARK}{math}{FORMULA_MARK}"
    body = etree.Element("body")
    paragraph = etree.SubElement(body, "p")
    paragraph.text = "resident of district "
    xref = etree.SubElement(paragraph, "xref")
    xref.set("ref-type", "bibr")
    xref.text = "see Bergstrom 1995"
    xref.tail = f" or district {token}. precisely {token}, the role"
    repaired = promote_encoded_formulas(
        etree.fromstring(etree.tostring(body, encoding="unicode").encode("utf-8"))
    )
    paragraph = repaired.find("p")
    formulas = paragraph.findall("inline-formula")
    assert [item.get("id") for item in formulas] == ["e5", "e5"]
    assert paragraph.find("xref").text == "see Bergstrom 1995"
    assert FORMULA_MARK not in "".join(paragraph.itertext())
    assert "mml:math" not in (paragraph.text or "")
    assert "mml:math" not in (paragraph.find("xref").tail or "")
