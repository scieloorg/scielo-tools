from unittest.mock import MagicMock, patch

import pytest
import requests

from front.exceptions import (
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)
from front.providers.http import Provider


@pytest.fixture
def llama_settings(settings):
    settings.FRONT_ENABLED = True
    settings.FRONT_URL = "http://llama.example:11434"
    settings.FRONT_MODEL = "llama3.2:3b"
    settings.FRONT_TIMEOUT = 30
    settings.FRONT_TOKEN = ""
    settings.FRONT_NUM_CTX = 8192
    settings.FRONT_KEEP_ALIVE = "-1"
    return settings


def test_http_provider_requires_url(settings):
    settings.FRONT_ENABLED = True
    settings.FRONT_URL = ""

    with pytest.raises(FrontLlamaMisconfiguredError):
        Provider([], {"type": "json_object"})


def test_http_provider_disabled(settings):
    settings.FRONT_ENABLED = False
    settings.FRONT_URL = "http://llama.example:11434"

    with pytest.raises(FrontLlamaDisabledError):
        Provider([], {"type": "json_object"})


def test_http_provider_chat_success(llama_settings):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "message": {"content": '{"titles":[]}'},
    }

    with patch(
        "front.providers.http.requests.post", return_value=mock_response
    ) as post:
        provider = Provider(
            [{"role": "system", "content": "sys"}],
            {"type": "json_object"},
        )
        result = provider.run("Título de teste")

    assert result == {
        "choices": [{"message": {"content": '{"titles":[]}'}}],
    }
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://llama.example:11434/api/chat"
    assert kwargs["json"]["model"] == "llama3.2:3b"
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["keep_alive"] == -1
    assert kwargs["headers"] == {}


def test_http_provider_unavailable(llama_settings):
    with patch(
        "front.providers.http.requests.post",
        side_effect=requests.ConnectionError("down"),
    ):
        provider = Provider([], {"type": "json_object"})
        with pytest.raises(FrontLlamaUnavailableError):
            provider.run("Título")
