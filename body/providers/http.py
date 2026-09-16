import logging
import time

import requests

from body.exceptions import (
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
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

        if not getattr(settings, "BODY_ENABLED", True):
            raise BodyLlamaDisabledError("Body Llama is disabled.")

        self.url = (getattr(settings, "BODY_URL", "") or "").rstrip("/")
        if not self.url:
            raise BodyLlamaMisconfiguredError(
                "BODY_URL is required when Body Llama is enabled."
            )

        self.model = getattr(settings, "BODY_MODEL", "") or "llama3.2:3b"
        self.timeout = getattr(settings, "BODY_TIMEOUT", 300)
        self.token = getattr(settings, "BODY_TOKEN", "") or ""
        self.num_ctx = int(getattr(settings, "BODY_NUM_CTX", 32768) or 32768)
        raw_keep_alive = getattr(settings, "BODY_KEEP_ALIVE", "-1")
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
            "Body Llama chat via %s model=%s. Preview: %r",
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
            payload_out = resp.json()
            response_text = payload_out.get("message", {}).get("content") or ""
            done_reason = payload_out.get("done_reason") or ""
        except requests.RequestException as exc:
            logger.error("Body Llama HTTP error: %s", exc)
            raise BodyLlamaUnavailableError(
                f"Body Llama service unavailable: {exc}"
            ) from exc

        elapsed = time.monotonic() - started
        logger.info(
            "Body Llama chat: %d chars in %.2fs done_reason=%s",
            len(response_text),
            elapsed,
            done_reason,
        )
        return {"choices": [{"message": {"content": response_text}}], "done_reason": done_reason}
