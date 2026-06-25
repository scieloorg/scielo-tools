from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from spsvalidator.db.repository import insert_validation_result
from spsvalidator.domain.validation import validate_sps_zip


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_pointer:
        for chunk in iter(lambda: file_pointer.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compute_status(rows: list[dict], exceptions: list[dict]) -> str:
    if rows:
        return "invalid"
    if exceptions:
        return "error"
    return "valid"


def run_validation(
    db_path: str, uploaded_file, zip_only_message: str | None = None
) -> dict:
    filename = uploaded_file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise ValueError(zip_only_message or "Only SPS .zip files are supported.")
    with tempfile.TemporaryDirectory(prefix="spsvalidator-") as temp_dir:
        zip_path = os.path.join(temp_dir, Path(filename).name)
        uploaded_file.save(zip_path)
        result = validate_sps_zip(zip_path)
        rows = result["rows"]
        exceptions = result["exceptions"]
        articles = result["articles"]
        status = _compute_status(rows, exceptions)
        history_id = insert_validation_result(
            db_path=db_path,
            package_name=Path(filename).name,
            package_sha256=_sha256_of_file(zip_path),
            rows=rows,
            exceptions=exceptions,
            articles=articles,
            status=status,
        )
    return {
        "history_id": history_id,
        "status": status,
        "rows": rows,
        "exceptions": exceptions,
        "articles": articles,
        "issues_count": len(rows),
        "exceptions_count": len(exceptions),
        "xml_count": len(articles),
    }
