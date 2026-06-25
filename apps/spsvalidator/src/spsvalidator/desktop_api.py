from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from spsvalidator.db.repository import get_validation_details
from spsvalidator.domain.export import build_validation_csv


def _reveal_in_file_manager(path: str) -> None:
    target = Path(path)
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", "-R", str(target)], check=False)
    elif system == "Windows":
        subprocess.run(["explorer", "/select,", str(target)], check=False)
    else:
        subprocess.run(["xdg-open", str(target.parent)], check=False)


class DesktopApi:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def save_validation_csv(self, history_id: str) -> dict:
        details = get_validation_details(self.db_path, history_id)
        if details is None:
            return {"ok": False, "error": "not_found"}
        csv_content = build_validation_csv(details["rows"])
        package_stem = details["package_name"].rsplit(".", 1)[0]
        save_filename = f"{package_stem}.validation.csv"
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        target_path = downloads_dir / save_filename
        target_path.write_text(csv_content, encoding="utf-8")
        _reveal_in_file_manager(str(target_path))
        return {"ok": True, "path": str(target_path)}
