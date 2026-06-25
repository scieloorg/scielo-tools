from __future__ import annotations

from pathlib import Path

from flask import Flask, request

from spsvalidator.build_metadata import get_footer_build_label
from spsvalidator.db.repository import init_db
from spsvalidator.version import APP_DISPLAY_NAME
from spsvalidator.web.i18n import LANGUAGE_OPTIONS, get_translations, normalize_language
from spsvalidator.web.routes import web_blueprint


def create_app(data_dir: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.secret_key = "spsvalidator-local-secret"
    target_dir = Path(data_dir) if data_dir else Path.home() / ".spsvalidator"
    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / "spsvalidator.sqlite3"
    init_db(str(db_path))
    app.config["DB_PATH"] = str(db_path)
    app.config["APP_DISPLAY_NAME"] = APP_DISPLAY_NAME

    @app.context_processor
    def inject_app_info():
        language = normalize_language(request.cookies.get("lang"))
        translations = get_translations(language)
        return {
            "app_display_name": app.config["APP_DISPLAY_NAME"],
            "current_language": language,
            "language_options": LANGUAGE_OPTIONS,
            "t": translations,
            "footer_build_label": get_footer_build_label(language, translations),
        }

    app.register_blueprint(web_blueprint)
    return app
