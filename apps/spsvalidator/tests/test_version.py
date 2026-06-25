import tomllib
from pathlib import Path

from spsvalidator.version import APP_DISPLAY_NAME, __version__


def test_version_matches_pyproject():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected = tomllib.load(pyproject_path.open("rb"))["project"]["version"]
    assert __version__ == expected
    assert APP_DISPLAY_NAME == f"SPSValidator-v{expected}"
