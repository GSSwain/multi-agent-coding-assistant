#!/bin/bash
set -e

echo "=== Local Gemma Setup Script ==="

# Check if brew is installed
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew is not installed. Please install Homebrew first."
    exit 1
fi

# Check if ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "Ollama is not installed. Installing Ollama via Homebrew..."
    brew install ollama
else
    echo "Ollama is already installed at: $(command -v ollama)"
fi

# Check if Ollama service is already reachable on the default API port.
# This avoids relying on Homebrew service management when the binary was installed
# outside of Homebrew (for example, via the official macOS installer).
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama service is already running."
else
    echo "Checking/Starting Ollama service..."
    if command -v brew >/dev/null 2>&1 && brew list --versions ollama >/dev/null 2>&1; then
        echo "Starting Ollama daemon via Homebrew service..."
        brew services start ollama || true
    else
        echo "Starting Ollama daemon directly with the installed binary..."
        ollama serve >/tmp/ollama-setup.log 2>&1 &
    fi

    echo "Waiting for Ollama service to start..."
    for _ in {1..30}; do
        if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            echo "Ollama service is ready."
            break
        fi
        sleep 1
    done
fi

# Pull the gemma2:2b model
echo "Pulling Gemma model (gemma2:2b)..."
ollama pull gemma2:2b

echo "=== Local Gemma Setup Complete ==="
