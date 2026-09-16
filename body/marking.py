import json
import logging

from body.exceptions import (
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
)
from body.prompts import MESSAGES, RESPONSE_FORMAT
from body.providers import get_provider
from body.utils import (
    apply_outline,
    section_from_plain_text,
    split_body_sections,
)

logger = logging.getLogger(__name__)


def mark_body(body_text):
    from body.data_utils import parse_marked

    try:
        parts = split_body_sections(body_text)
        if not parts:
            parts = [{"title": "", "text": str(body_text or "")}]
        skeleton = {"sections": []}
        for part in parts:
            heading = str(part.get("title") or "").strip()
            skeleton["sections"].append(
                section_from_plain_text(heading, part.get("text") or "")
            )
        marker = get_provider(MESSAGES, RESPONSE_FORMAT, max_tokens=4000)
        output = marker.run(str(body_text or ""))
        done_reason = str(output.get("done_reason") or "")
        raw = ""
        for item in output.get("choices") or []:
            raw = item.get("message", {}).get("content", "") or ""
            break
        outline = None
        if done_reason != "length":
            outline = parse_marked(raw)
        if outline is None:
            logger.warning(
                "Body Llama outline fallback done_reason=%s chars=%d",
                done_reason,
                len(raw),
            )
        else:
            skeleton = apply_outline(skeleton, outline)
        return json.dumps(skeleton)
    except (
        BodyLlamaDisabledError,
        BodyLlamaMisconfiguredError,
        BodyLlamaUnavailableError,
    ):
        raise
    except Exception:
        logger.exception("Unexpected error marking body")
        raise BodyLlamaUnavailableError("Body Llama returned an unexpected error")
