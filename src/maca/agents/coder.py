import difflib
from typing import Any, Dict, List, Optional

from maca.agents.base import BaseAgent
from maca.todo import format_compact_todo, init_todo_file, read_todo_file, update_todo_progress


class BaseCoderAgent(BaseAgent):
    """Abstract base coder agent consolidating common file formatting methods."""

    def __init__(
        self,
        name: str,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            name, model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

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

    def _format_todo_context(self, todo_content: Optional[str]) -> str:
        if not todo_content:
            return ""
        compact_todo = format_compact_todo(todo_content, min_completed_to_collapse=2)
        return (
            f"\n\nCurrent Todo Progress Checklist (.maca/<task>/coder.todo):\n{compact_todo}\n"
            "CONTINUATION INSTRUCTION: Items marked [x] are ALREADY COMPLETED. Do NOT start over. "
            "Continue the task based on the pending [ ] items and any nudge feedback above."
        )

    def compute_file_blocks(
        self, files: Dict[str, str], repo_files_content: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Compute the file and line blocks modified or added in each file."""
        file_blocks: Dict[str, List[Dict[str, Any]]] = {}
        normalized_repo_content: Dict[str, str] = {}
        if repo_files_content:
            for k, v in repo_files_content.items():
                normalized_repo_content[k.strip().replace("\\", "/").lstrip("/")] = v

        for rel_path, new_content in files.items():
            clean_rel_path = rel_path.strip().replace("\\", "/").lstrip("/")
            new_lines = new_content.splitlines(keepends=True)

            old_content = ""
            if normalized_repo_content and clean_rel_path in normalized_repo_content:
                old_content = normalized_repo_content[clean_rel_path]
            else:
                existing = self.read_file(clean_rel_path)
                if not existing.startswith("Error"):
                    old_content = existing

            if not old_content:
                file_blocks[clean_rel_path] = [
                    {
                        "start_line": 1,
                        "end_line": max(1, len(new_lines)),
                        "tag": "created",
                        "code": new_content,
                    }
                ]
            else:
                old_lines = old_content.splitlines(keepends=True)
                matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
                blocks: List[Dict[str, Any]] = []

                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag != "equal":
                        start_line = j1 + 1
                        end_line = max(j1 + 1, j2)
                        code_snippet = "".join(new_lines[j1:j2])
                        blocks.append(
                            {
                                "start_line": start_line,
                                "end_line": end_line,
                                "tag": tag,
                                "code": code_snippet,
                            }
                        )

                if not blocks:
                    blocks = [
                        {
                            "start_line": 1,
                            "end_line": max(1, len(new_lines)),
                            "tag": "full",
                            "code": new_content,
                        }
                    ]

                file_blocks[clean_rel_path] = blocks

        return file_blocks


class SimpleCoderAgent(BaseCoderAgent):
    def __init__(
        self,
        name: str,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            name, model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Software Coder Agent. Your job is to implement the changes outlined in the plan "
            "while strictly adhering to clean code practices.\n\n"
            "LANGUAGE & FRAMEWORK FIDELITY:\n"
            "- Strictly generate code using the programming language, framework, build tools, and file structure "
            "requested in the task and plan (e.g., Java with pom.xml or build.gradle for Spring Boot, TypeScript/JavaScript for React, Go for Go).\n"
            "- NEVER generate Python code (.py) when another language or framework is requested (e.g., Spring Boot requires Java/Kotlin, NOT Python).\n"
            "- Follow standard directory conventions and idiomatic best practices for the target language (e.g., src/main/java/... for Java Maven/Gradle projects).\n\n"
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
        todo_content: Optional[str] = None,
        allowed_directory: Optional[str] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(repo_files_content)
        todo_context = self._format_todo_context(todo_content)

        eff_allowed_dir = allowed_directory or getattr(self, "allowed_directory", ".")
        allowed_dir_context = ""
        if eff_allowed_dir and eff_allowed_dir != ".":
            allowed_dir_context = (
                f"\n\nAllowed Reading Directory: {eff_allowed_dir} (Files read must reside under this directory).\n"
                f"Workspace Modification Boundary: You can modify or create files within the workspace root ('{self.repo_path}')."
            )

        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Implementation Plan:\n{plan}\n"
            f"{todo_context}\n"
            f"{allowed_dir_context}\n"
            f"{files_context}\n"
            "Please implement the changes using clean code principles, adhering strictly to the requested programming language and framework. Output the files using the requested [FILE: path] format."
        )

    def run(
        self,
        task_description: str,
        plan: str = "",
        repo_files_content: Optional[Dict[str, str]] = None,
        history: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        nudge: Optional[str] = None,
        allowed_directory: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        plan_or_spec = plan or kwargs.get("spec", "")
        todo_content = None

        if task_name:
            if nudge:
                update_todo_progress(self.repo_path, task_name, "coder", nudge_feedback=nudge)
            todo_content = init_todo_file(self.repo_path, task_name, "coder", plan_or_spec)

        eff_dir = allowed_directory or kwargs.get("allowed_files") or self.allowed_directory
        prompt = self._build_prompt(
            task_description=task_description,
            plan=plan_or_spec,
            repo_files_content=repo_files_content,
            history=history,
            todo_content=todo_content,
            allowed_directory=eff_dir if isinstance(eff_dir, str) else None,
        )
        system_instruction = self._build_system_instruction()

        try:
            response = str(self.model_client.generate(prompt, system_instruction))
        except Exception as e:
            raise RuntimeError(f"Agent {self.name} failed during generation: {e}") from e

        if task_name:
            parsed = self.parse_files(response)
            if parsed:
                update_todo_progress(self.repo_path, task_name, "coder", generated_files=parsed)

        return response


class SpecCoderAgent(BaseCoderAgent):
    def __init__(
        self,
        name: str,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            name, model_client, repo_path=repo_path, allowed_directory=allowed_directory
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are a Software Coder Agent. Your job is to implement the changes outlined in the specification "
            "while strictly adhering to clean code practices.\n\n"
            "LANGUAGE & FRAMEWORK FIDELITY:\n"
            "- Strictly generate code using the programming language, framework, build tools, and file structure "
            "requested in the task and specification (e.g., Java with pom.xml or build.gradle for Spring Boot, TypeScript/JavaScript for React, Go for Go).\n"
            "- NEVER generate Python code (.py) when another language or framework is requested (e.g., Spring Boot requires Java/Kotlin, NOT Python).\n"
            "- Follow standard directory conventions and idiomatic best practices for the target language (e.g., src/main/java/... for Java Maven/Gradle projects).\n\n"
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
        todo_content: Optional[str] = None,
        allowed_directory: Optional[str] = None,
    ) -> str:
        history_context = self._format_history(history)
        files_context = self._format_files_context(repo_files_content)
        todo_context = self._format_todo_context(todo_content)

        eff_allowed_dir = allowed_directory or getattr(self, "allowed_directory", ".")
        allowed_dir_context = ""
        if eff_allowed_dir and eff_allowed_dir != ".":
            allowed_dir_context = (
                f"\n\nAllowed Reading Directory: {eff_allowed_dir} (Files read must reside under this directory).\n"
                f"Workspace Modification Boundary: You can modify or create files within the workspace root ('{self.repo_path}')."
            )

        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Technical Specification:\n{spec}\n"
            f"{todo_context}\n"
            f"{allowed_dir_context}\n"
            f"{files_context}\n"
            "Please implement the changes using clean code principles, adhering strictly to the requested programming language and framework. Output the files using the requested [FILE: path] format."
        )

    def run(
        self,
        task_description: str,
        spec: str = "",
        repo_files_content: Optional[Dict[str, str]] = None,
        history: Optional[List[str]] = None,
        task_name: Optional[str] = None,
        nudge: Optional[str] = None,
        allowed_directory: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        plan_or_spec = spec or kwargs.get("plan", "")
        todo_content = None

        if task_name:
            if nudge:
                update_todo_progress(self.repo_path, task_name, "coder", nudge_feedback=nudge)
            todo_content = init_todo_file(self.repo_path, task_name, "coder", plan_or_spec)

        eff_dir = allowed_directory or kwargs.get("allowed_files") or self.allowed_directory
        prompt = self._build_prompt(
            task_description=task_description,
            spec=plan_or_spec,
            repo_files_content=repo_files_content,
            history=history,
            todo_content=todo_content,
            allowed_directory=eff_dir if isinstance(eff_dir, str) else None,
        )
        system_instruction = self._build_system_instruction()

        try:
            response = str(self.model_client.generate(prompt, system_instruction))
        except Exception as e:
            raise RuntimeError(f"Agent {self.name} failed during generation: {e}") from e

        if task_name:
            parsed = self.parse_files(response)
            if parsed:
                update_todo_progress(self.repo_path, task_name, "coder", generated_files=parsed)

        return response


if __name__ == "__main__":
    import json
    import sys

    from maca.models.factory import get_model_client

    payload = json.loads(sys.stdin.read())
    args = payload.get("args", {})
    context = args.get("context", {})
    client = get_model_client(args.get("model_name"))
    repo_path = args.get("repo_path") or context.get("repo_path", ".")
    coder_type = args.get("coder_type", "SIMPLE")
    task_name = args.get("task_name") or context.get("task_name", "")
    task_desc = args.get("task_description") or context.get("task", "")
    plan = args.get("plan") or context.get("plan", "")
    spec = args.get("spec") or context.get("spec", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."
    nudge = args.get("nudge", "")

    agent: BaseCoderAgent
    if coder_type == "SIMPLE":
        agent = SimpleCoderAgent(
            "SimpleCoder", client, repo_path=repo_path, allowed_directory=allowed_dir
        )
        result = agent.run(
            task_description=task_desc,
            plan=plan,
            repo_files_content=args.get("repo_files_content"),
            history=args.get("history"),
            task_name=task_name,
            nudge=nudge,
            allowed_directory=allowed_dir,
        )
    else:
        agent = SpecCoderAgent(
            "SpecCoder", client, repo_path=repo_path, allowed_directory=allowed_dir
        )
        result = agent.run(
            task_description=task_desc,
            spec=spec,
            repo_files_content=args.get("repo_files_content"),
            history=args.get("history"),
            task_name=task_name,
            nudge=nudge,
            allowed_directory=allowed_dir,
        )

    parsed_files = agent.parse_files(result)
    file_blocks = agent.compute_file_blocks(parsed_files, args.get("repo_files_content"))
    todo_content = read_todo_file(repo_path, task_name, "coder") if task_name else None
    json.dump(
        {
            "result": result,
            "files": parsed_files,
            "file_blocks": file_blocks,
            "todo": todo_content,
            "agent": "coder",
            "completed": bool(parsed_files),
            "update": {
                "files_count": len(parsed_files),
                "files": list(parsed_files.keys()),
                "file_blocks": file_blocks,
            },
        },
        sys.stdout,
    )
