import os

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

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")

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

def validate_config(complexity, selected_agent=None):
    """Validate that the selected agent has the required configuration.

    Args:
        complexity: The evaluated task complexity level.
        selected_agent: The agent name that was selected for this task
                        (e.g. "GEMINI", "CLAUDE"). If None, falls back to
                        legacy behaviour of requiring Gemini for non-SIMPLE tasks.
    """
    if complexity == "SIMPLE":
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
