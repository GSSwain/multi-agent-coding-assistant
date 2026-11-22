from typing import Any, List, Optional

from maca.agents.base import BaseAgent
from maca.todo import write_todo_file


class PlannerAgent(BaseAgent):
    def __init__(
        self,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            "Planner", model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a technical Planner Agent. Your job is to analyze the user request "
            "and create a structured markdown implementation plan. "
            "Do NOT write any code implementation or scripts. Only write the steps and "
            "identify which files need to be created or modified.\n\n"
            "LANGUAGE & FRAMEWORK FIDELITY:\n"
            "- Identify the target programming language, framework, and build tools requested by the user "
            "(e.g., Java with Maven/pom.xml or Gradle/build.gradle for Spring Boot; TypeScript/JavaScript for React/Node; Go for Go; Python for Python).\n"
            "- Plan standard project scaffolding, build configurations (e.g. pom.xml or build.gradle for Spring Boot, package.json for Node), "
            "entrypoint files, and directory layouts (e.g. src/main/java/... for Java) using idiomatic conventions and exact file extensions.\n"
            "- NEVER default to Python (.py) unless Python is explicitly requested or the task is completely language-agnostic."
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
            "Clearly indicate the files to be created or modified using [NEW] and [MODIFY] tags. "
            "Ensure all planned files match the target programming language and framework conventions requested."
        )

    def run(
        self,
        task_description: str,
        repo_files: Optional[List[str]] = None,
        history: Optional[List[str]] = None,
        task_name: Optional[str] = None,
    ) -> str:
        system_instruction = self._build_system_instruction()
        prompt = self._build_prompt(task_description, repo_files=repo_files, history=history)
        try:
            plan = str(self.model_client.generate(prompt, system_instruction))
        except Exception as e:
            raise RuntimeError(f"Agent {self.name} failed during generation: {e}") from e

        if task_name:
            todo_text = (
                f"# Todo Progress for task: {task_name} (planner)\n"
                f"- [x] Inspect repository files\n"
                f"- [x] Generate structured markdown plan\n"
            )
            write_todo_file(self.repo_path, task_name, "planner", todo_text)

        return plan


if __name__ == "__main__":
    import json
    import sys

    from maca.models.factory import get_model_client

    payload = json.loads(sys.stdin.read())
    args = payload.get("args", {})
    context = args.get("context", {})
    client = get_model_client(args.get("model_name"))
    repo_path = args.get("repo_path") or context.get("repo_path", ".")
    task_name = args.get("task_name") or context.get("task_name", "")
    task_desc = args.get("task_description") or context.get("task", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."

    agent = PlannerAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
    repo_files = args.get("repo_files") or agent.list_files()
    result = agent.run(
        task_description=task_desc,
        repo_files=repo_files,
        history=args.get("history"),
        task_name=task_name,
    )
    json.dump(
        {
            "result": result,
            "agent": "planner",
            "completed": True,
            "update": {
                "plan": result,
                "allowed_directory": allowed_dir,
            },
        },
        sys.stdout,
    )
