#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ ! -f "$ROOT_DIR/.venv/bin/activate" ]; then
  echo "Virtual environment not found. Run ./local/scripts/install.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"
exec maca "$@"
