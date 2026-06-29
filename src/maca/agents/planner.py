from typing import Any, List, Optional

from maca.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    def __init__(self, model_client: Any, repo_path: str = "."):
        super().__init__("Planner", model_client, repo_path=repo_path)

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a technical Planner Agent. Your job is to analyze the user request "
            "and create a structured markdown implementation plan. "
            "Do NOT write any code implementation or scripts. Only write the steps and "
            "identify which files need to be created or modified."
        )

    def _build_prompt(
        self,
        task_description: str,
        repo_files: Optional[List[str]] = None,
        history: Optional[List[str]] = None,
    ) -> str:
        files_str = "\n".join(repo_files) if repo_files else "Empty repository"
        history_str = ""
        if history:
            history_str = "\n\nPrevious Conversation History:\n" + "\n".join(history)

        return (
            f"User Task: {task_description}{history_str}\n\n"
            f"Current Files in Repository:\n{files_str}\n\n"
            "Please output a detailed implementation plan in markdown format. "
            "Clearly indicate the files to be created or modified using [NEW] and [MODIFY] tags."
        )
