import tempfile
import zipfile
from pathlib import Path

import pytest

from spsvalidator.domain.validation import validate_sps_zip


@pytest.fixture
def fixture_zip_path(tmp_path):
    fixture_path = (
        Path(__file__).resolve().parents[3] / "fixtures" / "xml" / "dias_2023.xml"
    )
    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(
        zip_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.write(fixture_path, "dias_2023.xml")
    return zip_path


def test_validate_sps_zip_runs_with_packtools(fixture_zip_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / fixture_zip_path.name
        target.write_bytes(fixture_zip_path.read_bytes())
        result = validate_sps_zip(str(target))
    assert result["articles"]
    assert result["articles"][0]["title"]
