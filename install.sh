#!/usr/bin/env bash
# PostLens installer for macOS and Linux
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install it from https://www.python.org/downloads/"
  exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "PostLens needs Python 3.10 or newer (found $("$PY" --version))."; exit 1; }

echo "[1/3] Creating a private Python environment in .venv"
[ -d .venv ] || "$PY" -m venv .venv

echo "[2/3] Installing Python packages"
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] Downloading the browser PostLens uses (about 150 MB, one time)"
if [ "$(uname)" = "Linux" ]; then
  .venv/bin/python -m playwright install --with-deps chromium || .venv/bin/python -m playwright install chromium
else
  .venv/bin/python -m playwright install chromium
fi

echo
echo "Done. Start PostLens with: ./run.sh"
