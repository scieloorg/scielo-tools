from __future__ import annotations

import argparse
import socket
import threading
import time
from pathlib import Path
from wsgiref.simple_server import make_server

import webview

from spsvalidator.app import create_app
from spsvalidator.desktop_api import DesktopApi
from spsvalidator.version import APP_DISPLAY_NAME


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(app, host: str, port: int) -> None:
    server = make_server(host, port, app)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(prog="spsvalidator")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    app = create_app()
    if args.browser:
        app.run(host=args.host, port=args.port or 5000, debug=False)
        return

    db_path = app.config["DB_PATH"]
    host = args.host
    port = args.port or _free_port()
    thread = threading.Thread(target=_serve, args=(app, host, port), daemon=True)
    thread.start()
    time.sleep(0.4)
    icon_path = Path(__file__).resolve().parent / "web" / "static" / "img" / "icon.png"
    window_kwargs = {
        "title": APP_DISPLAY_NAME,
        "url": f"http://{host}:{port}",
        "width": 1360,
        "height": 900,
    }
    if icon_path.is_file():
        window_kwargs["icon"] = str(icon_path)
    window_kwargs["js_api"] = DesktopApi(db_path)
    webview.create_window(**window_kwargs)
    webview.start()


if __name__ == "__main__":
    main()
