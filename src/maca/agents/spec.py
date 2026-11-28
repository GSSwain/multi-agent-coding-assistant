from typing import Any, List, Optional

from maca.agents.base import BaseAgent
from maca.todo import write_todo_file


class SpecAgent(BaseAgent):
    def __init__(
        self,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            "SpecWriter", model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Technical Specification Agent. Your job is to analyze the user request "
            "and the provided implementation plan, and generate a detailed technical specification. "
            "The specification should outline exactly what needs to be implemented, the expected "
            "behavior, and the specific file changes required. "
            "Do NOT write the actual code. Focus on the requirements, constraints, and architecture.\n\n"
            "LANGUAGE & FRAMEWORK FIDELITY:\n"
            "- Strictly preserve the programming language, framework, build tools, and directory structure "
            "specified in the plan or task (e.g., Java with Maven/Gradle for Spring Boot, TypeScript for React/Next.js).\n"
            "- Specify exact file paths, package declarations, dependencies, and configuration appropriate for the target ecosystem.\n"
            "- NEVER substitute or default to Python when another language or framework is requested."
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
            "Please output a detailed technical specification in markdown format based on this plan. "
            "Ensure all technical specifications, file paths, and dependencies reflect the requested language and framework."
        )

    def run(
        self,
        task_description: str,
        plan: str,
        history: Optional[List[str]] = None,
        task_name: Optional[str] = None,
    ) -> str:
        system_instruction = self._build_system_instruction()
        prompt = self._build_prompt(task_description, plan, history=history)
        spec = self._generate(prompt, system_instruction)

        if task_name:
            todo_text = (
                f"# Todo Progress for task: {task_name} (spec)\n"
                f"- [x] Analyze implementation plan\n"
                f"- [x] Generate detailed technical specification\n"
            )
            write_todo_file(self.repo_path, task_name, "spec", todo_text)

        return spec


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
    plan = args.get("plan") or context.get("plan", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."

    agent = SpecAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
    result = agent.run(
        task_description=task_desc,
        plan=plan,
        history=args.get("history"),
        task_name=task_name,
    )
    json.dump(
        {
            "result": result,
            "agent": "spec",
            "completed": True,
            "update": {
                "spec": result,
                "allowed_directory": allowed_dir,
            },
        },
        sys.stdout,
    )
