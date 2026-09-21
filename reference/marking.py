import json
import logging

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


def mark_reference(reference_text):
    try:
        reference_marker = get_provider(MESSAGES, RESPONSE_FORMAT)
        output = reference_marker.run(reference_text)
        for item in output.get("choices", []):
            yield item.get("message", {}).get("content", "")

    except (
        ReferenceLlamaDisabledError,
        ReferenceLlamaMisconfiguredError,
        ReferenceLlamaUnavailableError,
    ) as exc:
        logger.error(
            "Error marking reference via Llama: %s — ref=%s", exc, reference_text
        )
        raise

    except Exception as exc:
        logger.exception("Unexpected error marking reference: ref=%s", reference_text)
        yield f"An unexpected error occurred: {str(exc)}"


def mark_reference_texts(texts):
    lines = list(texts)
    if not lines:
        return []

    batch_size = max(1, int(getattr(settings, "REFERENCE_BATCH_SIZE", 10) or 10))
    marked = []
    for start in range(0, len(lines), batch_size):
        chunk = lines[start : start + batch_size]
        if len(chunk) == 1:
            choices = list(mark_reference(chunk[0]))
            marked.append(choices[0] if choices else None)
            continue

        batch_contents = None
        try:
            reference_marker = get_provider(MESSAGES, BATCH_RESPONSE_FORMAT)
            numbered = "\n".join(
                f"{index}. {line}" for index, line in enumerate(chunk, start=1)
            )
            user_input = (
                "Extract each numbered line. Respond ONLY with a JSON object "
                '{"results":[...]} with exactly one object per line in the same '
                'order. Use {"is_reference": false} for non-citations.\n\n'
                f"{numbered}"
            )
            output = reference_marker.run(user_input)
            content = ""
            for item in output.get("choices", []):
                content = item.get("message", {}).get("content", "")
                break
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
        except (
            ReferenceLlamaDisabledError,
            ReferenceLlamaMisconfiguredError,
            ReferenceLlamaUnavailableError,
        ):
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
        else:
            marked.extend(batch_contents)

    return marked


def mark_references(reference_block):
    lines = parse_reference_list(reference_block)
    for ref_row, content in zip(lines, mark_reference_texts(lines), strict=False):
        yield {
            "references": ref_row,
            "choices": [content] if content is not None else [],
        }
