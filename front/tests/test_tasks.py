from unittest.mock import MagicMock

from front.tasks import mark_front_text


def test_mark_front_text_calls_resolve(monkeypatch):
    def fake_resolve(
        text,
        user=None,
        output_type="json",
        language=None,
        counts=None,
        on_progress=None,
    ):
        if on_progress is not None:
            on_progress(50)
        return {"data": {"titles": [{"text": text}]}}

    monkeypatch.setattr("front.tasks.resolve_front_result", fake_resolve)
    monkeypatch.setattr(mark_front_text, "update_state", MagicMock())
    result = mark_front_text.run(
        "Hello front",
        language="en",
        counts={"fig_count": "1"},
    )
    assert result["data"]["titles"][0]["text"] == "Hello front"
    mark_front_text.update_state.assert_called()
