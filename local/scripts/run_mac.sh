#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$SCRIPT_DIR/run.sh" ]; then
  exec "$SCRIPT_DIR/run.sh" "$@"
else
  exec bash "$SCRIPT_DIR/run.sh" "$@"
fi
