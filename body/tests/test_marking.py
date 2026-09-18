import json

from body.marking import mark_body
from body.utils import (
    apply_body_rules,
    apply_outline,
    sec_type_from_title,
    section_from_plain_text,
    split_body_sections,
)


def test_mark_body_one_call_keeps_source_paragraphs(monkeypatch):
    calls = []
    outline = {
        "sections": [
            {
                "title": "Introduction",
                "sec_type": "intro",
                "content": [{"type": "p", "text": "REWRITTEN BY LLAMA"}],
            },
            {"title": "Methods", "sec_type": "methods"},
        ]
    }

    class FakeProvider:
        def run(self, user_input):
            calls.append(user_input)
            return {
                "choices": [{"message": {"content": json.dumps(outline)}}],
                "done_reason": "stop",
            }

    monkeypatch.setattr(
        "body.marking.get_provider",
        lambda *args, **kwargs: FakeProvider(),
    )
    source = "Introduction\nOriginal paragraph from the article.\n" "Methods\nA study."
    marked = json.loads(mark_body(source))
    assert len(calls) == 1
    assert calls[0] == source
    texts = [
        block.get("text")
        for section in marked["sections"]
        for block in section.get("content") or []
        if block.get("type") == "p"
    ]
    assert "Original paragraph from the article." in texts
    assert "A study." in texts
    assert "REWRITTEN BY LLAMA" not in texts
    assert marked["sections"][0]["sec_type"] == "intro"
    assert marked["sections"][1]["sec_type"] == "methods"


def test_mark_body_falls_back_to_source_outline(monkeypatch):
    class FakeProvider:
        def run(self, user_input):
            return {
                "choices": [{"message": {"content": "not-json"}}],
                "done_reason": "length",
            }

    monkeypatch.setattr(
        "body.marking.get_provider",
        lambda *args, **kwargs: FakeProvider(),
    )
    marked = json.loads(
        mark_body(
            "Introduction\nHello Figure 1.\nFigure 1. A map of the area.\n"
            "Methods\nA study."
        )
    )
    assert [section["title"] for section in marked["sections"]] == [
        "Introduction",
        "Methods",
    ]
    assert marked["sections"][0]["sec_type"] == "intro"
    fig = [
        block
        for block in marked["sections"][0]["content"]
        if block.get("type") == "fig"
    ]
    assert fig and fig[0]["caption"] == "A map of the area."


def test_apply_outline_sets_sec_type_without_touching_content():
    parts = split_body_sections("Introduction\nKeep me.\nMethods\nAlso keep.")
    skeleton = {
        "sections": [
            section_from_plain_text(part["title"], part["text"]) for part in parts
        ]
    }
    overlay = apply_outline(
        skeleton,
        {
            "sections": [
                {
                    "title": "Introduction",
                    "sec_type": "intro",
                    "content": [{"type": "p", "text": "NOPE"}],
                },
                {"title": "Methods", "sec_type": "methods"},
            ]
        },
    )
    assert overlay["sections"][0]["content"][0]["text"] == "Keep me."
    assert overlay["sections"][0]["sec_type"] == "intro"
    assert overlay["sections"][1]["sec_type"] == "methods"


def test_sec_type_from_title_material_and_methods():
    assert sec_type_from_title("Material and Methods") == "materials|methods"
    assert sec_type_from_title("Materials and Methods") == "materials|methods"
    assert sec_type_from_title("Material e Métodos") == "materials|methods"


def test_apply_outline_keeps_skeleton_sec_type():
    skeleton = {
        "sections": [
            {
                "title": "Material and Methods",
                "sec_type": "materials|methods",
                "content": [{"type": "p", "text": "A study."}],
                "sections": [],
            }
        ]
    }
    overlay = apply_outline(
        skeleton,
        {
            "sections": [
                {"title": "Material and Methods", "sec_type": "methods"},
            ]
        },
    )
    assert overlay["sections"][0]["sec_type"] == "materials|methods"


def test_apply_outline_copies_data_availability_specific_use():
    skeleton = {
        "sections": [
            {
                "title": "Data Availability",
                "content": [{"type": "p", "text": "See SciELO Data."}],
                "sections": [],
            }
        ]
    }
    overlay = apply_outline(
        skeleton,
        {
            "sections": [
                {
                    "title": "Data Availability",
                    "sec_type": "data-availability",
                    "specific_use": "data-available",
                }
            ]
        },
    )
    assert overlay["sections"][0]["sec_type"] == "data-availability"
    assert overlay["sections"][0]["specific_use"] == "data-available"


def test_sec_type_from_title_tail_sections():
    assert sec_type_from_title("Acknowledgments") == "acknowledgments"
    assert sec_type_from_title("Supplementary Material") == "supplementary-material"
    assert sec_type_from_title("Data Availability") == "data-availability"


def test_apply_body_rules_enriches_tail_sections():
    marked = apply_body_rules(
        {
            "sections": [
                {
                    "title": "Supplementary Material",
                    "content": [
                        {
                            "type": "p",
                            "text": "See Supplementary Material S2 for tables.",
                        }
                    ],
                    "sections": [],
                },
                {
                    "title": "Data Availability",
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
                },
            ]
        },
        "",
    )
    assert marked["sections"][0]["sec_type"] == "supplementary-material"
    assert "parts" not in marked["sections"][0]["content"][0]
    assert marked["sections"][1]["sec_type"] == "data-availability"
    assert (
        marked["sections"][1]["specific_use"] == "data-available-upon-request"
    )
