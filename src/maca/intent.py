import re

INTENT_CONTINUE = "CONTINUE"
INTENT_NEW_TASK = "NEW_TASK"

_CONTINUE_PHRASES = frozenset(
    {
        "continue",
        "resume",
        "continue task",
        "continue the task",
        "continue my task",
        "continue last task",
        "continue the last task",
        "continue previous task",
        "continue the previous task",
        "continue where we left off",
        "continue from where we left off",
        "continue work",
        "continue working",
        "resume task",
        "resume the task",
        "resume my task",
        "resume last task",
        "resume the last task",
        "resume previous task",
        "resume the previous task",
        "resume where we left off",
        "resume from where we left off",
        "resume work",
        "resume working",
    }
)


class IntentClassifier:
    """Identifies high-level user prompt intent prior to task complexity classification."""

    def identify(self, prompt: str) -> str:
        """Return INTENT_CONTINUE for continue/resume prompts, otherwise INTENT_NEW_TASK."""
        if not prompt:
            return INTENT_NEW_TASK

        normalized = re.sub(r"\s+", " ", prompt.strip()).rstrip(".!?").strip().lower()
        if normalized in _CONTINUE_PHRASES:
            return INTENT_CONTINUE
        return INTENT_NEW_TASK
