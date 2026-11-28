from typing import Any, Dict, List, Optional

from maca.agents.base import BaseAgent
from maca.todo import write_todo_file


class ReviewerAgent(BaseAgent):
    def __init__(
        self,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            "Reviewer", model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Senior Reviewer Agent. Your job is to review the code generated for the task "
            "with a strict focus on clean code practices and technical correctness.\n\n"
            "CLEAN CODE AUDITING CRITERIA:\n"
            "1. Readability & Naming: Are variables, functions, and classes descriptively and consistently named?\n"
            "2. Modularity & Design: Is the code modular? Are functions doing only one thing (Single Responsibility)?\n"
            "3. Documentation & Type Hints: Are public interfaces properly documented with docstrings and type hints?\n"
            "4. Correctness & Quality: Are there syntax errors, logic bugs, bare excepts, or code duplication?\n"
            "5. Language & Framework Conformance: Verify that the code strictly adheres to the requested programming language, framework, "
            "and build ecosystem (e.g., Java for Spring Boot, TypeScript for React). Flag any incorrect language substitutions "
            "(e.g. generating Python for a Spring Boot task) as a critical failure and provide the corrected files in the requested language.\n\n"
            "If you find issues that violate these clean code principles or correctness, explain the issues clearly, "
            "and output the corrected files.\n\n"
            "CRITICAL: You MUST write the file identifier line in the EXACT format: [FILE: path/to/file.ext]\n"
            "Do NOT use markdown headers (like '## FILE: ...' or '# FILE: ...'), bullet points, or bold text. "
            "The parser WILL fail if you do not use square brackets [FILE: ...].\n\n"
            "Format:\n"
            "[FILE: path/to/file.ext]\n"
            "```language\n"
            "corrected code contents\n"
            "```\n\n"
            "If the code is perfect, output a summary and conclude with the word: APPROVED."
        )

    def _format_blocks_context(self, file_blocks: Optional[Dict[str, List[Dict[str, Any]]]]) -> str:
        if not file_blocks:
            return ""
        formatted = "\n\nTarget File and Line Blocks to Review:\n"
        for filepath, blocks in file_blocks.items():
            formatted += f"--- FILE: {filepath} ---\n"
            for block in blocks:
                s_line = block.get("start_line", 1)
                e_line = block.get("end_line", s_line)
                tag = block.get("tag", "modified")
                formatted += f"[Block: Lines {s_line}-{e_line} ({tag})]\n"
                code = block.get("code", "")
                formatted += f"{code}\n"
        return formatted

    def _build_prompt(
        self,
        task_description: str,
        generated_files: Dict[str, str],
        history: Optional[List[str]] = None,
        plan_or_spec: Optional[str] = None,
        file_blocks: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(generated_files)
        blocks_context = self._format_blocks_context(file_blocks)
        spec_context = ""
        if plan_or_spec:
            spec_context = f"\n\nImplementation Plan/Specification:\n{plan_or_spec}"

        return (
            f"User Task: {task_description}{history_context}{spec_context}\n\n"
            f"Generated Files to Review:\n{files_context}"
            f"{blocks_context}\n\n"
            "Please review the code changes and specific line blocks for correctness, logical bugs, and clean code practices. "
            "Suggest improvements and output corrected files if needed."
        )

    def run(
        self,
        task_description: str,
        generated_files: Dict[str, str],
        history: Optional[List[str]] = None,
        plan_or_spec: Optional[str] = None,
        file_blocks: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        task_name: Optional[str] = None,
    ) -> str:
        system_instruction = self._build_system_instruction()
        prompt = self._build_prompt(
            task_description=task_description,
            generated_files=generated_files,
            history=history,
            plan_or_spec=plan_or_spec,
            file_blocks=file_blocks,
        )
        response = self._generate(prompt, system_instruction)

        if task_name:
            approved = self.is_approved(response)
            status_box = "x" if approved else " "
            todo_text = (
                f"# Todo Progress for task: {task_name} (reviewer)\n"
                f"- [x] Audit code line blocks against clean code guidelines\n"
                f"- [x] Check syntax and logic correctness\n"
                f"- [{status_box}] Review decision: {'APPROVED' if approved else 'REVISIONS_REQUESTED'}\n"
            )
            write_todo_file(self.repo_path, task_name, "reviewer", todo_text)

        return response

    def _format_history(self, history: Optional[List[str]]) -> str:
        if not history:
            return ""
        return "\n\nPrevious Conversation History:\n" + "\n".join(history)

    def _format_files_context(self, files: Dict[str, str]) -> str:
        if not files:
            return ""
        formatted_files = ""
        for filepath, content in files.items():
            formatted_files += f"--- FILE: {filepath} ---\n{content}\n\n"
        return formatted_files

    def is_approved(self, response_text: str) -> bool:
        """Parses the reviewer response and determines if the implementation is approved."""
        return "APPROVED" in response_text.upper()


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
    plan_or_spec = args.get("plan_or_spec") or context.get("spec") or context.get("plan", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."

    agent = ReviewerAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
    result = agent.run(
        task_description=task_desc,
        generated_files=args.get("generated_files", {}),
        history=args.get("history"),
        plan_or_spec=plan_or_spec,
        file_blocks=args.get("file_blocks"),
        task_name=task_name,
    )
    is_approved = agent.is_approved(result)
    parsed_files = agent.parse_files(result)
    json.dump(
        {
            "result": result,
            "approved": is_approved,
            "files": parsed_files,
            "agent": "reviewer",
            "completed": is_approved,
            "update": {
                "approved": is_approved,
                "files_count": len(parsed_files),
                "files": list(parsed_files.keys()),
                "allowed_directory": allowed_dir,
            },
        },
        sys.stdout,
    )
