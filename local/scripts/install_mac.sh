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
fi

echo "Installation complete. Run: source .venv/bin/activate && maca"
