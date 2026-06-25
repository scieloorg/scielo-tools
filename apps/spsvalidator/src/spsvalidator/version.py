from __future__ import annotations

import tomllib
from pathlib import Path


def _load_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.is_file():
        with pyproject_path.open("rb") as file_pointer:
            data = tomllib.load(file_pointer)
        return str(data["project"]["version"])
    from spsvalidator import build_info

    return build_info.APP_VERSION


__version__ = _load_version()
APP_DISPLAY_NAME = f"SPSValidator-v{__version__}"
