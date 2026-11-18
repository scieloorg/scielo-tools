import inspect
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
)
from reference.marking import _reference_targets, reference_endpoints_label
from reference.providers.http import Provider


def _chat_response(content):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"message": {"content": content}}
    return mock_response


def _configure(settings, *, local=True, remote=False, remote_url=""):
    settings.REFERENCE_ENABLED = local
    settings.REFERENCE_URL = "http://local.example:11434" if local else ""
    settings.REFERENCE_MODEL = "local-model"
    settings.REFERENCE_TIMEOUT = 30
    settings.REFERENCE_TOKEN = ""
    settings.REFERENCE_NUM_CTX = 8192
    settings.REFERENCE_KEEP_ALIVE = "-1"
    settings.REFERENCE_REMOTE_ENABLED = remote
    settings.REFERENCE_REMOTE_URL = remote_url
    settings.REFERENCE_REMOTE_MODEL = "scielo-model"
    settings.REFERENCE_REMOTE_TIMEOUT = 30
    settings.REFERENCE_REMOTE_TOKEN = ""
    settings.REFERENCE_REMOTE_NUM_CTX = 8192
    settings.REFERENCE_REMOTE_KEEP_ALIVE = "-1"
    settings.REFERENCE_BATCH_SIZE = 10


def test_targets_do_not_take_manuscript_state():
    assert list(inspect.signature(_reference_targets).parameters) == []


def test_scielo_provider_uses_remote_url(settings):
    _configure(
        settings,
        remote=True,
        remote_url="http://scielo.example:11434",
    )
    provider = Provider([], {"type": "json_object"}, origin="scielo")
    assert provider.origin == "scielo"
    assert provider.url == "http://scielo.example:11434"
    assert provider.model == "scielo-model"


def test_scielo_provider_disabled(settings):
    _configure(settings, remote=False)
    with pytest.raises(ReferenceLlamaDisabledError):
        Provider([], None, origin="scielo")


def test_scielo_provider_requires_url(settings):
    _configure(settings, local=False, remote=True, remote_url="")
    with pytest.raises(ReferenceLlamaMisconfiguredError, match="REFERENCE_REMOTE_URL"):
        Provider([], None, origin="scielo")


def test_references_use_local_and_scielo_together(settings):
    _configure(
        settings,
        remote=True,
        remote_url="http://scielo.example:11434",
    )
    seen = []

    def post(url, json=None, headers=None, timeout=None):
        seen.append((url, json["model"], json["messages"][-1]["content"]))
        if url.startswith("http://local.example"):
            return _chat_response('{"reftype":"journal","source":"Local"}')
        return _chat_response('{"reftype":"journal","source":"SciELO"}')

    with patch("reference.providers.http.requests.post", side_effect=post):
        from reference.marking import mark_reference_texts

        result = mark_reference_texts(["Smith J. Nature. 2024."])

    assert json.loads(result[0])["source"] == "Local"
    assert reference_endpoints_label() == "both"
    assert [item[0] for item in seen] == [
        "http://local.example:11434/api/chat",
        "http://scielo.example:11434/api/chat",
    ]
    assert seen[0][1] == "local-model"
    assert seen[1][1] == "scielo-model"
    assert seen[0][2] == "Smith J. Nature. 2024."
    assert seen[1][2] == "Smith J. Nature. 2024."
    assert "Título inédito" not in seen[1][2]


def test_scielo_outage_keeps_local_reference_marking(settings):
    _configure(
        settings,
        remote=True,
        remote_url="http://scielo.example:11434",
    )

    def post(url, json=None, headers=None, timeout=None):
        if url.startswith("http://scielo.example"):
            raise requests.ConnectionError("down")
        return _chat_response('{"reftype":"journal","source":"Local"}')

    with patch("reference.providers.http.requests.post", side_effect=post):
        from reference.marking import mark_reference_texts

        result = mark_reference_texts(["Smith J. Nature. 2024."])

    assert json.loads(result[0])["source"] == "Local"
    assert reference_endpoints_label() == "local"


def test_local_outage_uses_scielo_reference_marking(settings):
    _configure(
        settings,
        remote=True,
        remote_url="http://scielo.example:11434",
    )

    def post(url, json=None, headers=None, timeout=None):
        if url.startswith("http://local.example"):
            raise requests.ConnectionError("down")
        return _chat_response('{"reftype":"journal","source":"SciELO"}')

    with patch("reference.providers.http.requests.post", side_effect=post):
        from reference.marking import mark_reference_texts

        result = mark_reference_texts(["Smith J. Nature. 2024."])

    assert json.loads(result[0])["source"] == "SciELO"
    assert reference_endpoints_label() == "scielo"


def test_remote_disabled_does_not_turn_off_local(settings):
    _configure(settings, remote=False, remote_url="http://scielo.example:11434")
    seen = []

    def post(url, json=None, headers=None, timeout=None):
        seen.append(url)
        return _chat_response('{"reftype":"journal","source":"Local"}')

    with patch("reference.providers.http.requests.post", side_effect=post):
        from reference.marking import mark_reference_texts

        result = mark_reference_texts(["Ref A", "Ref B"])

    assert [json.loads(item)["source"] for item in result] == ["Local", "Local"]
    assert seen
    assert all(url.startswith("http://local.example:11434/api/chat") for url in seen)
    assert reference_endpoints_label() == "local"


def test_batch_calls_local_and_scielo(settings):
    _configure(
        settings,
        remote=True,
        remote_url="http://scielo.example:11434",
    )
    seen = []

    def post(url, **kwargs):
        seen.append(url)
        payload = {
            "results": [
                {"reftype": "journal", "source": "Local"},
                {"reftype": "journal", "source": "Local"},
            ]
        }
        if url.startswith("http://scielo.example"):
            payload = {
                "results": [
                    {"reftype": "journal", "source": "SciELO"},
                    {"reftype": "journal", "source": "SciELO"},
                ]
            }
        return _chat_response(json.dumps(payload))

    with patch("reference.providers.http.requests.post", side_effect=post):
        from reference.marking import mark_reference_texts

        result = mark_reference_texts(["Ref A", "Ref B"])

    assert [json.loads(item)["source"] for item in result] == ["Local", "Local"]
    assert seen == [
        "http://local.example:11434/api/chat",
        "http://scielo.example:11434/api/chat",
    ]
    assert reference_endpoints_label() == "both"
