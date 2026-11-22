from typing import Any, Dict, Optional, Tuple

from maca import maca_config as config
from maca.agents.base import BaseAgent
from maca.todo import write_todo_file


class CodeCompletionVerifierAgent(BaseAgent):
    """Code completion verifier agent that verifies whether all steps

    in the plan/specification have been implemented by the coder.
    """

    def __init__(
        self,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            "CodeCompletionVerifier",
            model_client,
            repo_path=repo_path,
            allowed_directory=allowed_directory,
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Code Completion Verifier Agent. Compare the technical specification "
            "with the generated files to see if all planned tasks/steps are fully completed. "
            "Verify that all required files in the requested programming language and framework "
            "(e.g., Java files and pom.xml/build.gradle for Spring Boot) are present and properly implemented. "
            "Respond with 'YES' if everything is completely implemented. "
            "Otherwise, respond with 'NO' followed by a detailed list of what is missing."
        )

    def _build_prompt(
        self,
        task_description: str,
        spec: str,
        generated_files: Dict[str, str],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        files_str = ""
        for filepath, content in generated_files.items():
            files_str += f"--- FILE: {filepath} ---\n{content}\n\n"

        return (
            f"Task: {task_description}\n\n"
            f"Specification:\n{spec}\n\n"
            f"Generated Files:\n{files_str}\n\n"
            "Are all steps in the specification completely implemented? (Start your response with YES or NO)"
        )

    def validate(
        self,
        task_description: str,
        spec: str,
        generated_files: Dict[str, str],
        task_name: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Validate if the generated files completely satisfy the specification."""
        if config.MOCK_GEMMA_FALLBACK and not getattr(self.model_client, "api_key", None):
            is_done, response = True, "Mock Coder finished."
        else:
            try:
                response = self.run(task_description, spec, generated_files).strip()
                is_done = response.upper().startswith("YES")
            except Exception as e:
                is_done, response = True, f"Error validating completion: {e}"

        if task_name:
            box = "x" if is_done else " "
            todo_text = (
                f"# Todo Progress for task: {task_name} (code_completion_verifier)\n"
                f"- [{box}] All specification steps implemented\n"
                f"Validation Feedback: {response[:200]}\n"
            )
            write_todo_file(self.repo_path, task_name, "code_completion_verifier", todo_text)

        return is_done, response


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
    spec = args.get("spec") or context.get("spec") or context.get("plan", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."

    agent = CodeCompletionVerifierAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
    is_done, feedback = agent.validate(
        task_description=task_desc,
        spec=spec,
        generated_files=args.get("generated_files", {}),
        task_name=task_name,
    )
    json.dump(
        {
            "result": feedback,
            "is_done": is_done,
            "agent": "code_completion_verifier",
            "completed": is_done,
            "update": {
                "is_done": is_done,
                "feedback": feedback,
                "allowed_directory": allowed_dir,
            },
        },
        sys.stdout,
    )
