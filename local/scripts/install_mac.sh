#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$SCRIPT_DIR/install.sh" ]; then
  exec "$SCRIPT_DIR/install.sh" "$@"
else
  exec bash "$SCRIPT_DIR/install.sh" "$@"
fi
