#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install -e ".[dev]"
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed \
  --name spsvalidator \
  --icon src/spsvalidator/web/static/img/icon.png \
  --paths src \
  --collect-all packtools \
  --collect-all webview \
  --collect-data spsvalidator \
  --hidden-import pkg_resources \
  --hidden-import requests \
  --hidden-import tenacity \
  --hidden-import langdetect \
  --copy-metadata setuptools \
  src/spsvalidator/main.py
echo "Use linuxdeploy/appimagetool to convert dist/spsvalidator into AppImage."
