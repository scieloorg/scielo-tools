from unittest.mock import MagicMock

from reference.tasks import mark_reference_texts_task


def test_mark_reference_texts_task_reports_progress(monkeypatch):
    def fake_resolve(texts, user=None, output_type="json", on_progress=None):
        if on_progress is not None:
            on_progress(1, 2)
            on_progress(2, 2)
        return [{"mixed_citation": texts[0], "data": {"reftype": "journal"}}]

    monkeypatch.setattr("reference.tasks.resolve_references_result", fake_resolve)
    monkeypatch.setattr(mark_reference_texts_task, "update_state", MagicMock())
    result = mark_reference_texts_task.run(["Smith J. Nature. 2024."])
    assert result[0]["data"]["reftype"] == "journal"
    calls = mark_reference_texts_task.update_state.call_args_list
    states = [call.kwargs.get("state") for call in calls]
    assert "PROGRESS" in states
    metas = [call.kwargs.get("meta") or {} for call in calls]
    assert any(item.get("done") == 2 and item.get("total") == 2 for item in metas)
