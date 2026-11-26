#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  if python -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.9+ is required. Install it first from https://www.python.org/downloads/" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
  echo "Python 3.9 or higher is required. Install it from https://www.python.org/downloads/" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install hatchling
python -m pip install -e .

echo "Installing dev dependencies..."
python -m pip install -r requirements-dev.txt

echo "Setting up pre-commit hooks..."
pre-commit install

echo "Running static analysis (Ruff, Mypy & Bandit)..."
if ! ruff check src/; then
  echo "Build failed: Ruff linting errors found." >&2
  exit 1
fi

if ! mypy src/; then
  echo "Build failed: Mypy type-checking errors found." >&2
  exit 1
fi

if ! bandit -c pyproject.toml -r src/; then
  echo "Build failed: Bandit security issues found." >&2
  exit 1
fi

if [ -x "$ROOT_DIR/local/scripts/setup_gemma.sh" ]; then
  "$ROOT_DIR/local/scripts/setup_gemma.sh"
elif [ -f "$ROOT_DIR/local/scripts/setup_gemma.sh" ]; then
  bash "$ROOT_DIR/local/scripts/setup_gemma.sh"
fi

echo "Installation complete. Run: ./local/scripts/run.sh (or: source .venv/bin/activate && maca)"
