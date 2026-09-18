from unittest.mock import MagicMock, patch

import pytest
import requests

from body.exceptions import (
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
)
from body.providers.http import Provider


@pytest.fixture
def llama_settings(settings):
    settings.BODY_ENABLED = True
    settings.BODY_URL = "http://llama.example:11434"
    settings.BODY_MODEL = "llama3.2:3b"
    settings.BODY_TIMEOUT = 30
    settings.BODY_TOKEN = ""
    settings.BODY_NUM_CTX = 16384
    settings.BODY_KEEP_ALIVE = "-1"
    return settings


def test_http_provider_requires_url(settings):
    settings.BODY_ENABLED = True
    settings.BODY_URL = ""

    with pytest.raises(BodyLlamaMisconfiguredError):
        Provider([], {"type": "json_object"})


def test_http_provider_disabled(settings):
    settings.BODY_ENABLED = False
    settings.BODY_URL = "http://llama.example:11434"

    with pytest.raises(BodyLlamaDisabledError):
        Provider([], {"type": "json_object"})


def test_http_provider_chat_success(llama_settings):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "message": {"content": '{"sections":[]}'},
    }

    with patch("body.providers.http.requests.post", return_value=mock_response) as post:
        provider = Provider(
            [{"role": "system", "content": "sys"}],
            {"type": "json_object"},
        )
        result = provider.run("INTRODUÇÃO\nTexto")

    assert result == {
        "choices": [{"message": {"content": '{"sections":[]}'}}],
        "done_reason": "",
    }
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://llama.example:11434/api/chat"
    assert kwargs["json"]["model"] == "llama3.2:3b"
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["keep_alive"] == -1
    assert kwargs["json"]["think"] is False
    assert kwargs["headers"] == {}


def test_http_provider_unavailable(llama_settings):
    with patch(
        "body.providers.http.requests.post",
        side_effect=requests.ConnectionError("down"),
    ):
        provider = Provider([], {"type": "json_object"})
        with pytest.raises(BodyLlamaUnavailableError):
            provider.run("INTRODUÇÃO")
