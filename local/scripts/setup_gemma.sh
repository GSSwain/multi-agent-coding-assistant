#!/usr/bin/env bash
set -euo pipefail

echo "=== Local Gemma Setup Script ==="

MODEL="${OLLAMA_MODEL:-gemma2:2b}"
OLLAMA_TAGS_URL="http://127.0.0.1:11434/api/tags"

is_ollama_ready() {
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$OLLAMA_TAGS_URL" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$OLLAMA_TAGS_URL" >/dev/null 2>&1
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)' "$OLLAMA_TAGS_URL" >/dev/null 2>&1
  else
    return 1
  fi
}

# Check if ollama is installed
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Ollama is not installed. Installing Ollama via Homebrew..."
    brew install ollama
  elif [ "$(uname -s)" = "Linux" ] && command -v curl >/dev/null 2>&1; then
    echo "Ollama is not installed. Installing Ollama via official Linux install script..."
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "Error: Ollama is not installed and could not be installed automatically." >&2
    echo "Please install Ollama from https://ollama.com/download and re-run this script." >&2
    exit 1
  fi
else
  echo "Ollama is already installed at: $(command -v ollama)"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Error: Ollama installation finished, but 'ollama' is not in PATH." >&2
  echo "Add Ollama to your PATH or install from https://ollama.com/download and re-run." >&2
  exit 1
fi

# Check if Ollama service is already reachable on the default API port.
if is_ollama_ready; then
  echo "Ollama service is already running."
else
  echo "Checking/Starting Ollama service..."
  if command -v brew >/dev/null 2>&1 && brew list --versions ollama >/dev/null 2>&1; then
    echo "Starting Ollama daemon via Homebrew service..."
    if ! brew services start ollama >/dev/null 2>&1; then
      echo "Could not start Homebrew service directly; starting ollama serve in the background..."
      ollama serve >/tmp/ollama-setup.log 2>&1 &
    fi
  elif [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1 && systemctl cat ollama.service >/dev/null 2>&1; then
    echo "Starting Ollama daemon via systemd..."
    if ! systemctl start ollama >/dev/null 2>&1; then
      echo "Could not start systemd service directly; starting ollama serve in the background..."
      ollama serve >/tmp/ollama-setup.log 2>&1 &
    fi
  else
    echo "Starting Ollama daemon directly with the installed binary..."
    ollama serve >/tmp/ollama-setup.log 2>&1 &
  fi

  echo "Waiting for Ollama service to start..."
  OLLAMA_READY=0
  for _ in {1..30}; do
    if is_ollama_ready; then
      echo "Ollama service is ready."
      OLLAMA_READY=1
      break
    fi
    sleep 1
  done

  if [ "$OLLAMA_READY" -ne 1 ]; then
    echo "Error: Timed out waiting for Ollama service at $OLLAMA_TAGS_URL" >&2
    echo "Check /tmp/ollama-setup.log or start Ollama manually with: ollama serve" >&2
    exit 1
  fi
fi

# Pull the configured Gemma model (default: gemma2:2b)
echo "Pulling Gemma model ($MODEL)..."
ollama pull "$MODEL"

echo "=== Local Gemma Setup Complete ==="
