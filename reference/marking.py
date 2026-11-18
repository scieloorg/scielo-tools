import contextvars
import json
import logging

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)
from reference.prompts import BATCH_RESPONSE_FORMAT, MESSAGES, RESPONSE_FORMAT
from reference.providers import get_provider
from reference.utils.references import parse_reference_list

logger = logging.getLogger(__name__)

_endpoints = contextvars.ContextVar("reference_mark_endpoints", default=None)

LLAMA_ERRORS = (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
    SoftTimeLimitExceeded,
)


def reset_reference_endpoints():
    _endpoints.set(set())


def reference_endpoints_label():
    current = _endpoints.get() or set()
    has_local = "local" in current
    has_scielo = "scielo" in current
    if has_local and has_scielo:
        return "both"
    if has_scielo:
        return "scielo"
    if has_local:
        return "local"
    return ""


def _reference_targets():
    local_enabled = getattr(settings, "REFERENCE_ENABLED", True)
    remote_enabled = bool(getattr(settings, "REFERENCE_REMOTE_ENABLED", False))
    remote_url = (getattr(settings, "REFERENCE_REMOTE_URL", "") or "").strip()
    targets = []
    if local_enabled:
        targets.append("local")
    if remote_enabled and remote_url:
        targets.append("scielo")
    elif remote_enabled and not local_enabled:
        targets.append("scielo")
    if not targets:
        raise ReferenceLlamaDisabledError("Reference Llama is disabled.")
    return targets


def _collect_reference_chats(messages, response_format, user_input, **kwargs):
    targets = _reference_targets()
    found = {}
    primary_error = None
    for origin in targets:
        try:
            provider = get_provider(messages, response_format, origin=origin, **kwargs)
            output = provider.run(user_input)
            content = ""
            for item in output.get("choices", []):
                content = item.get("message", {}).get("content", "") or ""
                break
            found[origin] = content
        except Exception as exc:
            if primary_error is None:
                primary_error = exc
            logger.error("Reference marking via %s failed: %s", origin, exc)
            if len(targets) == 1:
                raise
    responded = [origin for origin in targets if str(found.get(origin) or "").strip()]
    current = set(_endpoints.get() or ())
    current.update(responded)
    _endpoints.set(current)
    logger.info("Reference marking responded=%s", ",".join(responded) or "none")
    if "local" in responded:
        return found["local"]
    if "scielo" in responded:
        return found["scielo"]
    if primary_error is not None:
        raise primary_error
    raise ReferenceLlamaUnavailableError("Reference Llama returned empty content")


def mark_reference(reference_text):
    try:
        content = _collect_reference_chats(MESSAGES, RESPONSE_FORMAT, reference_text)
        if content:
            yield content

    except LLAMA_ERRORS as exc:
        logger.error(
            "Error marking reference via Llama: %s — ref=%s", exc, reference_text
        )
        raise

    except Exception as exc:
        logger.exception("Unexpected error marking reference: ref=%s", reference_text)
        yield f"An unexpected error occurred: {str(exc)}"


def mark_reference_texts(texts, on_progress=None):
    lines = list(texts)
    if not lines:
        return []

    reset_reference_endpoints()
    batch_size = max(1, int(getattr(settings, "REFERENCE_BATCH_SIZE", 10) or 10))
    marked = []
    total = len(lines)
    if on_progress is not None:
        on_progress(0, total)
    for start in range(0, len(lines), batch_size):
        chunk = lines[start : start + batch_size]
        if len(chunk) == 1:
            choices = list(mark_reference(chunk[0]))
            marked.append(choices[0] if choices else None)
            if on_progress is not None:
                on_progress(len(marked), total)
            continue

        batch_contents = None
        try:
            numbered = "\n".join(
                f"{index}. {line}" for index, line in enumerate(chunk, start=1)
            )
            user_input = (
                "Extract each numbered line. Respond ONLY with a JSON object "
                '{"results":[...]} with exactly one object per line in the same '
                'order. Use {"is_reference": false} for non-citations.\n\n'
                f"{numbered}"
            )
            content = _collect_reference_chats(
                MESSAGES, BATCH_RESPONSE_FORMAT, user_input
            )
            parsed = json.loads(content) if content else None
            results = None
            if isinstance(parsed, list):
                results = parsed
            elif isinstance(parsed, dict):
                if isinstance(parsed.get("results"), list):
                    results = parsed["results"]
            if results is not None and len(results) == len(chunk):
                batch_contents = [
                    json.dumps(item) if isinstance(item, dict) else item
                    for item in results
                ]
        except LLAMA_ERRORS:
            raise
        except Exception:
            logger.exception(
                "Batch marking failed for %d references; falling back to one-by-one",
                len(chunk),
            )

        if batch_contents is None:
            logger.warning(
                "Batch mark unavailable for %d refs; falling back to one-by-one",
                len(chunk),
            )
            for line in chunk:
                choices = list(mark_reference(line))
                marked.append(choices[0] if choices else None)
                if on_progress is not None:
                    on_progress(len(marked), total)
        else:
            marked.extend(batch_contents)
            if on_progress is not None:
                on_progress(len(marked), total)

    return marked


def mark_references(reference_block):
    lines = parse_reference_list(reference_block)
    for ref_row, content in zip(lines, mark_reference_texts(lines), strict=False):
        yield {
            "references": ref_row,
            "choices": [content] if content is not None else [],
        }
