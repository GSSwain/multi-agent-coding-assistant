from typing import Any, Optional

from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient


def get_model_client(model_name: Optional[str] = None) -> Any:
    """Instantiate and return the appropriate model client based on model name."""
    if not model_name:
        return LocalGemmaClient()

    name = model_name.upper()
    if "GEMINI" in name:
        return GeminiClient()
    elif "CLAUDE" in name:
        return ClaudeClient()
    elif "GEMMA" in name:
        return LocalGemmaClient()
    else:
        return LocalGemmaClient()
