from typing import Any, Dict, List, Optional

from maca.agents.base import BaseAgent


class BaseCoderAgent(BaseAgent):
    """Abstract base coder agent consolidating common file formatting methods."""

    def __init__(self, name: str, model_client: Any, repo_path: str = "."):
        super().__init__(name, model_client, repo_path=repo_path)

    def _format_history(self, history: Optional[List[str]]) -> str:
        if not history:
            return ""
        return "\n\nPrevious Conversation History:\n" + "\n".join(history)

    def _format_files_context(self, repo_files_content: Optional[Dict[str, str]]) -> str:
        if not repo_files_content:
            return ""
        formatted_files = "\n\nExisting File Contents:\n"
        for filepath, content in repo_files_content.items():
            formatted_files += f"--- FILE: {filepath} ---\n{content}\n\n"
        return formatted_files


class SimpleCoderAgent(BaseCoderAgent):
    def __init__(self, name: str, model_client: Any, repo_path: str = "."):
        super().__init__(name, model_client, repo_path=repo_path)

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Software Coder Agent. Your job is to implement the changes outlined in the plan "
            "while strictly adhering to clean code practices.\n\n"
            "CLEAN CODE GUIDELINES:\n"
            "- Modularity: Break code into small, single-purpose functions/classes.\n"
            "- Readability: Use clear, descriptive, and consistent variable/function names.\n"
            "- Documentation: Include concise docstrings and inline comments explaining complex logic.\n"
            "- Type Safety: Use type hints for function parameters and return types where applicable.\n"
            "- Error Handling: Handle potential exceptions gracefully (no bare except blocks).\n"
            "- Simplicity: Avoid over-engineering, code duplication, or spaghetti code.\n\n"
            "CRITICAL: You MUST write the file identifier line in the EXACT format: [FILE: path/to/file.ext]\n"
            "Do NOT use markdown headers (like '## FILE: ...' or '# FILE: ...'), bullet points, or bold text. "
            "The parser WILL fail if you do not use square brackets [FILE: ...].\n\n"
            "Format:\n"
            "[FILE: path/to/file.ext]\n"
            "```language\n"
            "code contents\n"
            "```\n\n"
            "Make sure to provide the entire, complete contents of the file. Do not use placeholders or ellipsis."
        )

    def _build_prompt(
        self,
        task_description: str,
        plan: str,
        repo_files_content: Optional[Dict[str, str]] = None,
        history: Optional[List[str]] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(repo_files_content)

        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Implementation Plan:\n{plan}\n"
            f"{files_context}\n"
            "Please implement the changes using clean code principles, and output the files using the requested [FILE: path] format."
        )


class SpecCoderAgent(BaseCoderAgent):
    def __init__(self, name: str, model_client: Any, repo_path: str = "."):
        super().__init__(name, model_client, repo_path=repo_path)

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Software Coder Agent. Your job is to implement the changes outlined in the specification "
            "while strictly adhering to clean code practices.\n\n"
            "CLEAN CODE GUIDELINES:\n"
            "- Modularity: Break code into small, single-purpose functions/classes.\n"
            "- Readability: Use clear, descriptive, and consistent variable/function names.\n"
            "- Documentation: Include concise docstrings and inline comments explaining complex logic.\n"
            "- Type Safety: Use type hints for function parameters and return types where applicable.\n"
            "- Error Handling: Handle potential exceptions gracefully (no bare except blocks).\n"
            "- Simplicity: Avoid over-engineering, code duplication, or spaghetti code.\n\n"
            "CRITICAL: You MUST write the file identifier line in the EXACT format: [FILE: path/to/file.ext]\n"
            "Do NOT use markdown headers (like '## FILE: ...' or '# FILE: ...'), bullet points, or bold text. "
            "The parser WILL fail if you do not use square brackets [FILE: ...].\n\n"
            "Format:\n"
            "[FILE: path/to/file.ext]\n"
            "```language\n"
            "code contents\n"
            "```\n\n"
            "Make sure to provide the entire, complete contents of the file. Do not use placeholders or ellipsis."
        )

    def _build_prompt(
        self,
        task_description: str,
        spec: str,
        repo_files_content: Optional[Dict[str, str]] = None,
        history: Optional[List[str]] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(repo_files_content)

        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Technical Specification:\n{spec}\n"
            f"{files_context}\n"
            "Please implement the changes using clean code principles, and output the files using the requested [FILE: path] format."
        )
