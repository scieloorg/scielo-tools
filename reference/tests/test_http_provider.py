from unittest.mock import MagicMock, patch

import pytest
import requests

from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)
from reference.providers.http import Provider


@pytest.fixture
def llama_settings(settings):
    settings.REFERENCE_ENABLED = True
    settings.REFERENCE_URL = "http://llama.example:11434"
    settings.REFERENCE_MODEL = "llama3.2:3b"
    settings.REFERENCE_TIMEOUT = 30
    settings.REFERENCE_TOKEN = ""
    settings.REFERENCE_NUM_CTX = 8192
    settings.REFERENCE_KEEP_ALIVE = "-1"
    return settings


def test_http_provider_requires_url(settings):
    settings.REFERENCE_ENABLED = True
    settings.REFERENCE_URL = ""

    with pytest.raises(ReferenceLlamaMisconfiguredError):
        Provider([], {"type": "json_object"})


def test_http_provider_disabled(settings):
    settings.REFERENCE_ENABLED = False
    settings.REFERENCE_URL = "http://llama.example:11434"

    with pytest.raises(ReferenceLlamaDisabledError):
        Provider([], {"type": "json_object"})


def test_http_provider_chat_success(llama_settings):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "message": {"content": '{"reftype":"journal"}'},
    }

    with patch(
        "reference.providers.http.requests.post", return_value=mock_response
    ) as post:
        provider = Provider(
            [{"role": "system", "content": "sys"}],
            {
                "type": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {"reftype": {"type": "string"}},
                    "required": ["reftype"],
                },
            },
        )
        result = provider.run("Smith J. Nature. 2024.")

    assert result == {
        "choices": [{"message": {"content": '{"reftype":"journal"}'}}],
    }
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://llama.example:11434/api/chat"
    assert kwargs["json"]["model"] == "llama3.2:3b"
    assert kwargs["json"]["options"]["num_ctx"] == 8192
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["keep_alive"] == -1
    assert kwargs["json"]["think"] is False
    assert kwargs["json"]["messages"][-1]["content"] == "Smith J. Nature. 2024."
    assert kwargs["headers"] == {}


def test_http_provider_sends_bearer_token(llama_settings):
    llama_settings.REFERENCE_TOKEN = "secret-token"
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"message": {"content": "{}"}}

    with patch(
        "reference.providers.http.requests.post", return_value=mock_response
    ) as post:
        provider = Provider([], None)
        provider.chat([{"role": "user", "content": "hi"}])

    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert "format" not in post.call_args.kwargs["json"]
    assert post.call_args.kwargs["json"]["keep_alive"] == -1


def test_http_provider_keep_alive_duration(llama_settings):
    llama_settings.REFERENCE_KEEP_ALIVE = "30m"
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"message": {"content": "{}"}}

    with patch(
        "reference.providers.http.requests.post", return_value=mock_response
    ) as post:
        Provider([], None).chat([{"role": "user", "content": "hi"}])

    assert post.call_args.kwargs["json"]["keep_alive"] == "30m"


def test_http_provider_omits_keep_alive_when_empty(llama_settings):
    llama_settings.REFERENCE_KEEP_ALIVE = ""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"message": {"content": "{}"}}

    with patch(
        "reference.providers.http.requests.post", return_value=mock_response
    ) as post:
        Provider([], None).chat([{"role": "user", "content": "hi"}])

    assert "keep_alive" not in post.call_args.kwargs["json"]


def test_http_provider_raises_on_http_error(llama_settings):
    with patch(
        "reference.providers.http.requests.post",
        side_effect=requests.ConnectionError("refused"),
    ):
        provider = Provider([], None)
        with pytest.raises(ReferenceLlamaUnavailableError):
            provider.chat([{"role": "user", "content": "hi"}])


def test_http_provider_raises_on_empty_content(llama_settings):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"message": {"content": "", "thinking": "..."}}

    with patch("reference.providers.http.requests.post", return_value=mock_response):
        provider = Provider([], None)
        with pytest.raises(ReferenceLlamaUnavailableError):
            provider.chat([{"role": "user", "content": "hi"}])
