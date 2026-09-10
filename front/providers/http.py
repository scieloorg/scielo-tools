import logging
import time

import requests

from front.exceptions import (
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)

logger = logging.getLogger(__name__)


class Provider:
    def __init__(
        self,
        messages,
        response_format,
        temperature=0.0,
        top_p=0.1,
        max_tokens=8000,
    ):
        from django.conf import settings

        self.messages = messages or []
        self.response_format = response_format
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

        if not getattr(settings, "FRONT_ENABLED", True):
            raise FrontLlamaDisabledError("Front Llama is disabled.")

        self.url = (getattr(settings, "FRONT_URL", "") or "").rstrip("/")
        if not self.url:
            raise FrontLlamaMisconfiguredError(
                "FRONT_URL is required when Front Llama is enabled."
            )

        self.model = getattr(settings, "FRONT_MODEL", "") or "llama3.2:3b"
        self.timeout = getattr(settings, "FRONT_TIMEOUT", 300)
        self.token = getattr(settings, "FRONT_TOKEN", "") or ""
        self.num_ctx = int(getattr(settings, "FRONT_NUM_CTX", 8192) or 8192)
        raw_keep_alive = getattr(settings, "FRONT_KEEP_ALIVE", "-1")
        if raw_keep_alive is None or raw_keep_alive == "":
            self.keep_alive = None
        else:
            try:
                self.keep_alive = int(raw_keep_alive)
            except (TypeError, ValueError):
                self.keep_alive = str(raw_keep_alive)

    def run(self, user_input):
        messages = self.messages.copy()
        messages.append({"role": "user", "content": user_input})
        return self.chat(messages)

    def chat(self, messages):
        started = time.monotonic()
        logger.info(
            "Front Llama chat via %s model=%s. Preview: %r",
            self.url,
            self.model,
            messages[-1]["content"][:150],
        )

        options = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "num_ctx": self.num_ctx,
        }
        if self.max_tokens:
            options["num_predict"] = self.max_tokens

        payload = {
            "model": self.model,
            "messages": messages,
            "options": options,
            "stream": False,
        }
        if self.response_format and self.response_format.get("type") == "json_object":
            payload["format"] = "json"
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = requests.post(
                f"{self.url}/api/chat",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            response_text = resp.json().get("message", {}).get("content") or ""
        except requests.RequestException as exc:
            logger.error("Front Llama HTTP error: %s", exc)
            raise FrontLlamaUnavailableError(
                f"Front Llama service unavailable: {exc}"
            ) from exc

        elapsed = time.monotonic() - started
        logger.info(
            "Front Llama chat: %d chars in %.2fs",
            len(response_text),
            elapsed,
        )
        return {"choices": [{"message": {"content": response_text}}]}
