import os

_gemini_key = None

def get_gemini_api_key():
    global _gemini_key
    if _gemini_key is not None:
        return _gemini_key
    _gemini_key = os.environ.get("GEMINI_API_KEY", "")
    return _gemini_key

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")

# If set to True, will mock Gemma/Gemini calls if unavailable/unconfigured
MOCK_GEMMA_FALLBACK = os.environ.get("MOCK_GEMMA_FALLBACK", "True").lower() == "true"

def validate_config(complexity):
    # Only SIMPLE tasks run Gemma (which is local and does not require API keys).
    # All other tasks (MEDIUM, COMPLEX, VERY_COMPLEX) route to Gemini.
    if complexity != "SIMPLE":
        if not get_gemini_api_key():
            raise ValueError(
                "GEMINI_API_KEY is not set in environment variables. "
                "Gemini is required for Medium, Complex, and Very Complex tasks."
            )

SANDBOX_READ_ONLY = False
