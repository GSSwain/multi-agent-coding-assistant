#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it first from https://www.python.org/downloads/macos/" >&2
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install hatchling
python -m pip install -e .

if [ -x "$ROOT_DIR/local/scripts/setup_gemma.sh" ]; then
  "$ROOT_DIR/local/scripts/setup_gemma.sh"
fi

echo "Installation complete. Run: source .venv/bin/activate && maca"
