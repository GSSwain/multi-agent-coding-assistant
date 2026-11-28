#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

CLI_MODEL="${OLLAMA_MODEL:-}"
HEADROOM_GB="${MACA_OS_HEADROOM_GB:-10}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --model)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "Error: --model requires a non-empty value." >&2
        exit 1
      fi
      CLI_MODEL="$2"
      shift 2
      ;;
    --model=*)
      CLI_MODEL="${1#*=}"
      if [ -z "$CLI_MODEL" ]; then
        echo "Error: --model requires a non-empty value." >&2
        exit 1
      fi
      shift
      ;;
    --headroom-gb)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "Error: --headroom-gb requires a numeric value." >&2
        exit 1
      fi
      HEADROOM_GB="$2"
      shift 2
      ;;
    --headroom-gb=*)
      HEADROOM_GB="${1#*=}"
      if [ -z "$HEADROOM_GB" ]; then
        echo "Error: --headroom-gb requires a numeric value." >&2
        exit 1
      fi
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--model <name>] [--headroom-gb <gb>]"
      exit 0
      ;;
    *)
      echo "Error: Unknown option: $1" >&2
      echo "Usage: $0 [--model <name>] [--headroom-gb <gb>]" >&2
      exit 1
      ;;
  esac
done

if ! LC_ALL=C awk -v v="$HEADROOM_GB" 'BEGIN { exit !(v ~ /^[0-9]+(\.[0-9]+)?$/) }' >/dev/null 2>&1; then
  echo "Error: --headroom-gb / MACA_OS_HEADROOM_GB must be a non-negative number (got: $HEADROOM_GB)." >&2
  exit 1
fi

echo "=== Local Gemma Setup Script ==="

OLLAMA_TAGS_URL="http://127.0.0.1:11434/api/tags"
SELECTOR_SCRIPT="$ROOT_DIR/src/maca/local_model_selector.py"

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

detect_total_mem_gb_shell() {
  if [ -r /proc/meminfo ]; then
    local mem_kb
    mem_kb="$(LC_ALL=C awk '/^MemTotal:/ { print $2; exit }' /proc/meminfo 2>/dev/null || true)"
    if [ -n "$mem_kb" ] && LC_ALL=C awk -v kb="$mem_kb" 'BEGIN { exit !(kb ~ /^[0-9]+$/ && kb > 0) }' >/dev/null 2>&1; then
      LC_ALL=C awk -v kb="$mem_kb" 'BEGIN { printf "%.1f", kb / 1048576.0 }'
      return 0
    fi
  fi
  if command -v sysctl >/dev/null 2>&1; then
    local mem_bytes
    mem_bytes="$(sysctl -n hw.memsize 2>/dev/null || true)"
    if [ -n "$mem_bytes" ] && LC_ALL=C awk -v b="$mem_bytes" 'BEGIN { exit !(b ~ /^[0-9]+$/ && b > 0) }' >/dev/null 2>&1; then
      LC_ALL=C awk -v b="$mem_bytes" 'BEGIN { printf "%.1f", b / 1073741824.0 }'
      return 0
    fi
  fi
  echo ""
}

format_gb_display() {
  local val="$1"
  if [ -z "$val" ] || [ "$val" = "None" ] || [ "$val" = "null" ] || [ "$val" = "unknown" ]; then
    echo "unknown"
  else
    echo "${val} GB"
  fi
}

PYTHON_BIN=""
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

SELECTED_OLLAMA_MODEL=""
SELECTED_OLLAMA_NUM_CTX=""
SELECTED_OLLAMA_KV_CACHE_TYPE="q8_0"
SELECTED_OLLAMA_FLASH_ATTENTION="1"
SELECTED_TOTAL_MEM_GB=""
SELECTED_OS_HEADROOM_GB="$HEADROOM_GB"
SELECTED_MODEL_BUDGET_GB=""

SELECTOR_USED=0
if [ -n "$PYTHON_BIN" ] && [ -f "$SELECTOR_SCRIPT" ]; then
  SELECTOR_ARGS=("--format" "shell" "--write-config" "--headroom-gb" "$HEADROOM_GB")
  if [ -n "$CLI_MODEL" ]; then
    SELECTOR_ARGS+=("--model" "$CLI_MODEL")
  fi
  if SELECTOR_OUT="$("$PYTHON_BIN" "$SELECTOR_SCRIPT" "${SELECTOR_ARGS[@]}" 2>/dev/null)"; then
    while IFS='=' read -r key val; do
      [ -z "$key" ] && continue
      key="${key#export }"
      val="${val%$'\r'}"
      val="${val#\'}"
      val="${val%\'}"
      val="${val#\"}"
      val="${val%\"}"
      case "$key" in
        SELECTED_OLLAMA_MODEL) SELECTED_OLLAMA_MODEL="$val" ;;
        SELECTED_OLLAMA_NUM_CTX) SELECTED_OLLAMA_NUM_CTX="$val" ;;
        SELECTED_OLLAMA_KV_CACHE_TYPE) SELECTED_OLLAMA_KV_CACHE_TYPE="$val" ;;
        SELECTED_OLLAMA_FLASH_ATTENTION) SELECTED_OLLAMA_FLASH_ATTENTION="$val" ;;
        SELECTED_TOTAL_MEM_GB) SELECTED_TOTAL_MEM_GB="$val" ;;
        SELECTED_OS_HEADROOM_GB) SELECTED_OS_HEADROOM_GB="$val" ;;
        SELECTED_MODEL_BUDGET_GB) SELECTED_MODEL_BUDGET_GB="$val" ;;
      esac
    done <<< "$SELECTOR_OUT"
    if [ -n "$SELECTED_OLLAMA_MODEL" ]; then
      SELECTOR_USED=1
    fi
  fi
fi

if [ "$SELECTOR_USED" -ne 1 ]; then
  SELECTED_TOTAL_MEM_GB="$(detect_total_mem_gb_shell)"
  SELECTED_OS_HEADROOM_GB="$(LC_ALL=C awk -v h="$HEADROOM_GB" 'BEGIN { printf "%.1f", h + 0.0 }')"
  SELECTED_OLLAMA_KV_CACHE_TYPE="q8_0"
  SELECTED_OLLAMA_FLASH_ATTENTION="1"

  if [ -n "$SELECTED_TOTAL_MEM_GB" ]; then
    SELECTED_MODEL_BUDGET_GB="$(LC_ALL=C awk -v t="$SELECTED_TOTAL_MEM_GB" -v h="$HEADROOM_GB" 'BEGIN { b = t - h; if (b < 0) b = 0; printf "%.1f", b }')"
    TIER_RESULT="$(LC_ALL=C awk -v t="$SELECTED_TOTAL_MEM_GB" -v h="$HEADROOM_GB" 'BEGIN {
      eff = t - (h - 10.0)
      if (eff >= 40.0) {
        print "gemma4:26b-a4b-it-q8_0 32768"
      } else if (eff >= 28.0) {
        print "gemma4:26b 16384"
      } else if (eff >= 16.0) {
        print "hf.co/crucible-labs/Gemma4-26B-A4B-REAP-25-GGUF:Q3_K-mixed 16384"
      } else if (eff >= 12.0) {
        print "gemma4:e4b 16384"
      } else {
        print "gemma4:e2b 8192"
      }
    }')"
    read -r TIER_MODEL TIER_NUM_CTX <<< "$TIER_RESULT"
  else
    SELECTED_MODEL_BUDGET_GB=""
    TIER_MODEL="gemma4:e2b"
    if [ -n "$CLI_MODEL" ]; then
      TIER_NUM_CTX="16384"
    else
      TIER_NUM_CTX="8192"
    fi
  fi

  if [ -n "$CLI_MODEL" ]; then
    SELECTED_OLLAMA_MODEL="$CLI_MODEL"
  else
    SELECTED_OLLAMA_MODEL="$TIER_MODEL"
  fi
  SELECTED_OLLAMA_NUM_CTX="$TIER_NUM_CTX"

  CONFIG_PATH="${MACA_LOCAL_MODEL_CONFIG:-$HOME/.maca/local_model.env}"
  mkdir -p "$(dirname "$CONFIG_PATH")"
  cat > "$CONFIG_PATH" <<EOF
OLLAMA_MODEL=$SELECTED_OLLAMA_MODEL
OLLAMA_NUM_CTX=$SELECTED_OLLAMA_NUM_CTX
OLLAMA_KV_CACHE_TYPE=$SELECTED_OLLAMA_KV_CACHE_TYPE
OLLAMA_FLASH_ATTENTION=$SELECTED_OLLAMA_FLASH_ATTENTION
EOF
fi

case "${SELECTED_OLLAMA_FLASH_ATTENTION:-1}" in
  0|false|False|FALSE|no|No|NO)
    SELECTED_OLLAMA_FLASH_ATTENTION="0"
    ;;
  *)
    SELECTED_OLLAMA_FLASH_ATTENTION="1"
    ;;
esac

SELECTED_OLLAMA_KV_CACHE_TYPE="${SELECTED_OLLAMA_KV_CACHE_TYPE:-q8_0}"
SELECTED_OLLAMA_NUM_CTX="${SELECTED_OLLAMA_NUM_CTX:-8192}"

export OLLAMA_FLASH_ATTENTION="$SELECTED_OLLAMA_FLASH_ATTENTION"
export OLLAMA_KV_CACHE_TYPE="$SELECTED_OLLAMA_KV_CACHE_TYPE"
export OLLAMA_CONTEXT_LENGTH="$SELECTED_OLLAMA_NUM_CTX"

echo "Detected system memory : $(format_gb_display "$SELECTED_TOTAL_MEM_GB")"
echo "Reserved OS headroom   : $(format_gb_display "$SELECTED_OS_HEADROOM_GB")"
echo "Available model budget : $(format_gb_display "$SELECTED_MODEL_BUDGET_GB")"
echo "Selected Gemma model   : $SELECTED_OLLAMA_MODEL"
echo "Ollama tuning          : KV_CACHE_TYPE=$OLLAMA_KV_CACHE_TYPE, FLASH_ATTENTION=$OLLAMA_FLASH_ATTENTION, CONTEXT_LENGTH=$OLLAMA_CONTEXT_LENGTH"

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

echo "Pulling Gemma model ($SELECTED_OLLAMA_MODEL)..."
ollama pull "$SELECTED_OLLAMA_MODEL"

echo "=== Local Gemma Setup Complete ==="
