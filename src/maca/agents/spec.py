from typing import Any, List, Optional

from maca.agents.base import BaseAgent


class SpecAgent(BaseAgent):
    def __init__(self, model_client: Any, repo_path: str = "."):
        super().__init__("SpecWriter", model_client, repo_path=repo_path)

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Technical Specification Agent. Your job is to analyze the user request "
            "and the provided implementation plan, and generate a detailed technical specification. "
            "The specification should outline exactly what needs to be implemented, the expected "
            "behavior, and the specific file changes required. "
            "Do NOT write the actual code. Focus on the requirements, constraints, and architecture."
        )

    def _build_prompt(
        self, task_description: str, plan: str, history: Optional[List[str]] = None
    ) -> str:
        history_str = ""
        if history:
            history_str = "\n\nPrevious Conversation History:\n" + "\n".join(history)

        return (
            f"User Task: {task_description}{history_str}\n\n"
            f"Implementation Plan:\n{plan}\n\n"
            "Please output a detailed technical specification in markdown format based on this plan."
        )
