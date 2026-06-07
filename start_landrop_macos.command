#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3, then run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

python3 -u landrop_web.py
