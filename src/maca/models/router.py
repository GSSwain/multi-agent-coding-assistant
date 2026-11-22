from typing import Any, Callable, Optional, Tuple

from maca import maca_config as config
from maca.health import BackendHealthService
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient


class ModelRouter:
    """Selects the optimal model client based on complexity, backend availability,

    and user-specified overrides.
    """

    @staticmethod
    def select_model(
        complexity: str,
        model_override: Optional[str] = None,
        is_gemini_online_fn: Optional[Callable[[], bool]] = None,
        is_claude_online_fn: Optional[Callable[[], bool]] = None,
    ) -> Tuple[str, Any]:
        """Returns (model_name, client_instance)."""
        if model_override:
            model_name = model_override.upper()
            if model_name.startswith("GEMINI"):
                config.validate_config(complexity, selected_agent="GEMINI")
                return model_name, GeminiClient()
            elif model_name.startswith("CLAUDE"):
                config.validate_config(complexity, selected_agent="CLAUDE")
                return model_name, ClaudeClient()
            elif model_name.startswith("GEMMA"):
                config.validate_config(complexity)
                return model_name, LocalGemmaClient()
            else:
                config.validate_config(complexity)
                return model_name, LocalGemmaClient()

        if complexity == "SIMPLE":
            return "GEMMA (LOCAL)", LocalGemmaClient()

        check_gemini = is_gemini_online_fn or BackendHealthService.is_gemini_online
        check_claude = is_claude_online_fn or BackendHealthService.is_claude_online

        gemini_online = check_gemini()
        claude_online = check_claude()

        if complexity == "MEDIUM":
            if gemini_online:
                config.validate_config(complexity, selected_agent="GEMINI")
                return "GEMINI (REMOTE)", GeminiClient()
            elif claude_online:
                config.validate_config(complexity, selected_agent="CLAUDE")
                return "CLAUDE (REMOTE)", ClaudeClient()
            else:
                config.validate_config(complexity)
                return "GEMMA (LOCAL)", LocalGemmaClient()
        else:  # COMPLEX and VERY_COMPLEX
            if claude_online:
                config.validate_config(complexity, selected_agent="CLAUDE")
                return "CLAUDE (REMOTE)", ClaudeClient()
            elif gemini_online:
                config.validate_config(complexity, selected_agent="GEMINI")
                return "GEMINI (REMOTE)", GeminiClient()
            else:
                config.validate_config(complexity)
                return "GEMMA (LOCAL)", LocalGemmaClient()
