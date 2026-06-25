Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Path $PSScriptRoot -Parent
Set-Location $RootDir

python -m pip install -e ".[dev]"
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed `
  --name spsvalidator `
  --icon src/spsvalidator/web/static/img/icon.png `
  --paths src `
  --collect-all packtools `
  --collect-all webview `
  --collect-data spsvalidator `
  --hidden-import pkg_resources `
  --hidden-import requests `
  --hidden-import tenacity `
  --hidden-import langdetect `
  --copy-metadata setuptools `
  src/spsvalidator/main.py
