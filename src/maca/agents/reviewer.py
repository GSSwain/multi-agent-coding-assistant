from typing import Any, Dict, List, Optional

from maca.agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    def __init__(self, model_client: Any, repo_path: str = "."):
        super().__init__("Reviewer", model_client, repo_path=repo_path)

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Senior Reviewer Agent. Your job is to review the code generated for the task "
            "with a strict focus on clean code practices and technical correctness.\n\n"
            "CLEAN CODE AUDITING CRITERIA:\n"
            "1. Readability & Naming: Are variables, functions, and classes descriptively and consistently named?\n"
            "2. Modularity & Design: Is the code modular? Are functions doing only one thing (Single Responsibility)?\n"
            "3. Documentation & Type Hints: Are public interfaces properly documented with docstrings and type hints?\n"
            "4. Correctness & Quality: Are there syntax errors, logic bugs, bare excepts, or code duplication?\n\n"
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

    def _build_prompt(
        self,
        task_description: str,
        generated_files: Dict[str, str],
        history: Optional[List[str]] = None,
        plan_or_spec: Optional[str] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(generated_files)
        spec_context = ""
        if plan_or_spec:
            spec_context = f"\n\nImplementation Plan/Specification:\n{plan_or_spec}"

        return (
            f"User Task: {task_description}{history_context}{spec_context}\n\n"
            f"Generated Files to Review:\n{files_context}"
            "Please review the code for correctness, logical bugs, and clean code practices. "
            "Suggest improvements and output corrected files if needed."
        )

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
