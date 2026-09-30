#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "PostLens is not installed yet. Run ./install.sh first."
  exit 1
fi
exec .venv/bin/python -m postlens "$@"
