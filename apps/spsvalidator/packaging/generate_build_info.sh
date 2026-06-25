#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT_DIR/src/spsvalidator/build_info.py"
cd "$ROOT_DIR"

APP_VERSION="$(python - <<'PY'
import tomllib
from pathlib import Path

with Path("pyproject.toml").open("rb") as file_pointer:
    data = tomllib.load(file_pointer)
print(data["project"]["version"])
PY
)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  MACOS_VERSION="$(sw_vers -productVersion)"
  MACOS_BUILD="$(sw_vers -buildVersion)"
  cat > "$TARGET" <<EOF
APP_VERSION = "${APP_VERSION}"
BUILD_MACOS_VERSION = "${MACOS_VERSION} (${MACOS_BUILD})"
BUILD_PLATFORM = "macOS"
EOF
else
  cat > "$TARGET" <<EOF
APP_VERSION = "${APP_VERSION}"
BUILD_MACOS_VERSION = "development"
BUILD_PLATFORM = "$(uname -s)"
EOF
fi
