#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${VENV:-.venv-build}"
APP_NAME="LanDrop"
ARTIFACT="dist/${APP_NAME}-macOS.zip"

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

python -m py_compile landrop.py landrop_core.py landrop_cli.py landrop_web.py test_landrop.py
python -m unittest

python -m PyInstaller --clean --noconfirm --name "$APP_NAME" --windowed landrop_web.py
ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "$ARTIFACT"

echo "Built $ARTIFACT"
