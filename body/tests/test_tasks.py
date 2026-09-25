from unittest.mock import MagicMock

from body.tasks import mark_body_text


def test_mark_body_text_calls_resolve(monkeypatch):
    def fake_resolve(
        text,
        user=None,
        output_type="json",
        language=None,
        tables=None,
        figures=None,
        image_hrefs=None,
    ):
        return {"data": {"sections": [{"title": text}]}}

    monkeypatch.setattr("body.tasks.resolve_body_result", fake_resolve)
    monkeypatch.setattr(mark_body_text, "update_state", MagicMock())
    result = mark_body_text.run("Introduction")
    assert result["data"]["sections"][0]["title"] == "Introduction"
    mark_body_text.update_state.assert_called()
