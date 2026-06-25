from __future__ import annotations

import csv
import io

VALIDATION_CSV_COLUMNS = [
    "group",
    "title",
    "parent",
    "parent_id",
    "parent_article_type",
    "item",
    "sub_item",
    "attribute",
    "validation_type",
    "response",
    "expected_value",
    "got_value",
    "advice",
]


def build_validation_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=VALIDATION_CSV_COLUMNS,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
