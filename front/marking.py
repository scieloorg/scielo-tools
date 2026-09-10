import logging

from front.exceptions import (
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)
from front.prompts import MESSAGES, RESPONSE_FORMAT
from front.providers import get_provider

logger = logging.getLogger(__name__)


def mark_front(front_text):
    try:
        marker = get_provider(MESSAGES, RESPONSE_FORMAT)
        output = marker.run(front_text)
        for item in output.get("choices", []):
            return item.get("message", {}).get("content", "")
        return ""
    except (
        FrontLlamaDisabledError,
        FrontLlamaMisconfiguredError,
        FrontLlamaUnavailableError,
    ):
        raise
    except Exception:
        logger.exception("Unexpected error marking front")
        raise FrontLlamaUnavailableError("Front Llama returned an unexpected error")
