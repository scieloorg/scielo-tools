from pathlib import Path

from spsvalidator.app import create_app
from spsvalidator.desktop_api import DesktopApi
from spsvalidator.services import validation_service


def test_save_validation_csv_writes_file(monkeypatch, tmp_path):
    app = create_app(str(tmp_path))
    db_path = app.config["DB_PATH"]
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "spsvalidator.desktop_api._reveal_in_file_manager",
        lambda path: None,
    )

    def fake_validate(zip_path: str):
        return {
            "rows": [{"group": "g", "title": "t", "response": "ERROR"}],
            "exceptions": [],
            "articles": [],
        }

    monkeypatch.setattr(validation_service, "validate_sps_zip", fake_validate)

    class UploadedFile:
        filename = "package.zip"

        def save(self, destination):
            Path(destination).write_bytes(b"zip")

    result = validation_service.run_validation(db_path, UploadedFile())
    api = DesktopApi(db_path)
    response = api.save_validation_csv(result["history_id"])
    target = tmp_path / "Downloads" / "package.validation.csv"
    assert response["ok"] is True
    assert target.is_file()
    assert "group,title" in target.read_text(encoding="utf-8")
