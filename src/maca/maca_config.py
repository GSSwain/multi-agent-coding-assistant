import math
import os
from typing import Optional, Tuple

from maca.local_model_selector import (
    OS_HEADROOM_GB,
    LocalModelSelection,
    load_local_model_config,
    select_gemma_model,
)

_gemini_key = None


def get_gemini_api_key():
    global _gemini_key
    if _gemini_key is not None:
        return _gemini_key
    _gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    return _gemini_key


_claude_key = None


def get_claude_api_key():
    global _claude_key
    if _claude_key is not None:
        return _claude_key
    _claude_key = os.environ.get("CLAUDE_API_KEY", "").strip()
    return _claude_key


def _resolve_ollama_settings() -> Tuple[str, int, str, bool]:
    """Resolve local Ollama model and runtime settings.

    Precedence:
    1. Explicit environment variables (`OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, etc.)
    2. Persisted local model config (`~/.maca/local_model.env` or `MACA_LOCAL_MODEL_CONFIG`)
    3. Automatic memory-aware Gemma 4 selection (`select_gemma_model()`)
    """
    persisted = load_local_model_config()
    try:
        headroom_gb = float(os.environ.get("MACA_OS_HEADROOM_GB", str(OS_HEADROOM_GB)))
    except ValueError:
        headroom_gb = OS_HEADROOM_GB

    selection: Optional[LocalModelSelection] = None

    def _get_selection() -> LocalModelSelection:
        nonlocal selection
        if selection is None:
            selection = select_gemma_model(headroom_gb=headroom_gb)
        return selection

    model = (
        os.environ.get("OLLAMA_MODEL", "").strip()
        or persisted.get("OLLAMA_MODEL", "").strip()
        or _get_selection().model
    )

    num_ctx: Optional[int] = None
    for raw_ctx in (
        os.environ.get("OLLAMA_NUM_CTX", "").strip(),
        persisted.get("OLLAMA_NUM_CTX", "").strip(),
    ):
        if raw_ctx:
            try:
                parsed = int(raw_ctx)
                if parsed > 0:
                    num_ctx = parsed
                    break
            except ValueError:
                pass
    if num_ctx is None:
        num_ctx = _get_selection().num_ctx

    kv_cache_type = (
        os.environ.get("OLLAMA_KV_CACHE_TYPE", "").strip()
        or persisted.get("OLLAMA_KV_CACHE_TYPE", "").strip()
        or "q8_0"
    )
    flash_raw = (
        os.environ.get("OLLAMA_FLASH_ATTENTION", "").strip()
        or persisted.get("OLLAMA_FLASH_ATTENTION", "").strip()
        or "1"
    )
    flash_attention = flash_raw.lower() in ("1", "true", "yes", "on")

    return model, num_ctx, kv_cache_type, flash_attention


OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_KV_CACHE_TYPE, OLLAMA_FLASH_ATTENTION = (
    _resolve_ollama_settings()
)

# Configurable timeouts (seconds) for cloud model API calls
try:
    GEMINI_TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "90"))
except ValueError:
    GEMINI_TIMEOUT_SECONDS = 90.0

try:
    CLAUDE_TIMEOUT_SECONDS = float(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "90"))
except ValueError:
    CLAUDE_TIMEOUT_SECONDS = 90.0

GEMINI_TIMEOUT = GEMINI_TIMEOUT_SECONDS
CLAUDE_TIMEOUT = CLAUDE_TIMEOUT_SECONDS

# Claude model to use for API calls
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# Gemini model to use for API calls
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

# If set to True, will mock Gemma/Gemini/Claude calls if unavailable/unconfigured
MOCK_GEMMA_FALLBACK = os.environ.get("MOCK_GEMMA_FALLBACK", "False").lower() == "true"

# Recency window (in minutes) used to disambiguate multiple recent tasks on 'continue'
try:
    CONTINUE_RECENT_WINDOW_MINUTES = float(os.environ.get("MACA_CONTINUE_WINDOW_MINUTES", "5"))
except ValueError:
    CONTINUE_RECENT_WINDOW_MINUTES = 5.0


def _parse_int_env(value: Optional[str], default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float_env(value: Optional[str], default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value.strip())
    except ValueError:
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def _parse_optional_nonneg_int_env(value: Optional[str]) -> Optional[int]:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


# Pre-flight context token budget settings to prevent silent local truncation
_raw_explicit_budget = os.environ.get("MACA_CONTEXT_TOKEN_BUDGET")
CONTEXT_TOKEN_BUDGET_OVERRIDE: Optional[int] = _parse_optional_nonneg_int_env(_raw_explicit_budget)

_raw_context_budget = _raw_explicit_budget
if _raw_context_budget is None or not _raw_context_budget.strip():
    _raw_context_budget = os.environ.get("OLLAMA_NUM_CTX")

_default_local_budget = OLLAMA_NUM_CTX if OLLAMA_NUM_CTX > 0 else 16384
CONTEXT_TOKEN_BUDGET: int = _parse_int_env(_raw_context_budget, _default_local_budget)
if CONTEXT_TOKEN_BUDGET < 0:
    CONTEXT_TOKEN_BUDGET = _default_local_budget

_raw_gemini_ctx = os.environ.get("MACA_GEMINI_CONTEXT_WINDOW")
GEMINI_CONTEXT_WINDOW: int = _parse_int_env(_raw_gemini_ctx, 50000)
if GEMINI_CONTEXT_WINDOW <= 0:
    GEMINI_CONTEXT_WINDOW = 50000

_raw_claude_ctx = os.environ.get("MACA_CLAUDE_CONTEXT_WINDOW")
CLAUDE_CONTEXT_WINDOW: int = _parse_int_env(_raw_claude_ctx, 50000)
if CLAUDE_CONTEXT_WINDOW <= 0:
    CLAUDE_CONTEXT_WINDOW = 50000

_raw_reserve_ratio = os.environ.get("MACA_CONTEXT_OUTPUT_RESERVE_RATIO")
CONTEXT_OUTPUT_RESERVE_RATIO: float = _parse_float_env(_raw_reserve_ratio, 0.30)

_raw_budget_enabled = os.environ.get("MACA_CONTEXT_BUDGET_ENABLED", "true").strip().lower()
CONTEXT_BUDGET_ENABLED: bool = _raw_budget_enabled not in {"false", "0", "no", "off"}


def validate_config(complexity, selected_agent=None):
    """Validate that the selected agent has the required configuration.

    Args:
        complexity: The evaluated task complexity level.
        selected_agent: The agent name that was selected for this task
                        (e.g. "GEMINI", "CLAUDE"). If None, falls back to
                        legacy behaviour of requiring Gemini for non-SIMPLE tasks.
    """
    if complexity == "SIMPLE" or selected_agent == "GEMMA":
        return  # Local Gemma, no API key needed

    if selected_agent == "CLAUDE":
        if not get_claude_api_key():
            raise ValueError(
                "CLAUDE_API_KEY is not set in environment variables. "
                "Claude is required for this task's complexity level."
            )
    elif selected_agent == "GEMINI":
        if not get_gemini_api_key():
            raise ValueError(
                "GEMINI_API_KEY is not set in environment variables. "
                "Gemini is required for this task's complexity level."
            )
    else:
        # Legacy fallback: require Gemini for any non-SIMPLE task
        if not get_gemini_api_key():
            raise ValueError(
                "GEMINI_API_KEY is not set in environment variables. "
                "Gemini is required for Medium, Complex, and Very Complex tasks."
            )


SANDBOX_READ_ONLY = False
