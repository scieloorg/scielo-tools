import logging
import time

import requests

from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)

logger = logging.getLogger(__name__)


class Provider:
    def __init__(
        self,
        messages,
        response_format,
        temperature=0.0,
        top_p=0.1,
        max_tokens=4000,
    ):
        from django.conf import settings

        self.messages = messages or []
        self.response_format = response_format
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

        if not getattr(settings, "REFERENCE_ENABLED", True):
            raise ReferenceLlamaDisabledError("Reference Llama is disabled.")

        self.url = (getattr(settings, "REFERENCE_URL", "") or "").rstrip("/")
        if not self.url:
            raise ReferenceLlamaMisconfiguredError(
                "REFERENCE_URL is required when Reference Llama is enabled."
            )

        self.model = getattr(settings, "REFERENCE_MODEL", "") or "llama3.2:3b"
        self.timeout = getattr(settings, "REFERENCE_TIMEOUT", 300)
        self.token = getattr(settings, "REFERENCE_TOKEN", "") or ""
        self.num_ctx = int(getattr(settings, "REFERENCE_NUM_CTX", 8192) or 8192)
        raw_keep_alive = getattr(settings, "REFERENCE_KEEP_ALIVE", "-1")
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
            "Reference Llama chat via %s model=%s. Preview: %r",
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
            "think": False,
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
            message = resp.json().get("message") or {}
            response_text = message.get("content") or ""
            if not str(response_text).strip():
                raise ReferenceLlamaUnavailableError(
                    "Reference Llama returned empty content"
                )
        except requests.RequestException as exc:
            logger.error("Reference Llama HTTP error: %s", exc)
            raise ReferenceLlamaUnavailableError(
                f"Reference Llama service unavailable: {exc}"
            ) from exc

        elapsed = time.monotonic() - started
        logger.info(
            "Reference Llama chat: %d chars in %.2fs",
            len(response_text),
            elapsed,
        )
        return {"choices": [{"message": {"content": response_text}}]}
