import abc
import os
import re
from typing import Any, Dict, List, Optional


class BaseAgent(abc.ABC):
    def __init__(
        self,
        name: str,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        self.name = name
        self.model_client = model_client
        self.repo_path = os.path.abspath(repo_path)
        self.allowed_directory = allowed_directory or "."

    @property
    def abs_allowed_directory(self) -> str:
        """Returns the absolute path of the allowed directory."""
        if os.path.isabs(self.allowed_directory):
            return os.path.abspath(self.allowed_directory)
        return os.path.abspath(os.path.join(self.repo_path, self.allowed_directory))

    @staticmethod
    def _is_windows_drive_path(path: str) -> bool:
        stripped = path.strip()
        return len(stripped) >= 2 and stripped[0].isalpha() and stripped[1] == ":"

    @staticmethod
    def _is_unc_path(path: str) -> bool:
        stripped = path.strip()
        return stripped.startswith(("\\\\", "//"))

    def _prepare_workspace_path(self, file_path: str) -> Optional[str]:
        """Prepare a path for joining with repo_path, rejecting cross-OS absolute escapes."""
        stripped = file_path.strip()
        if self._is_unc_path(stripped):
            return None
        if self._is_windows_drive_path(stripped):
            if os.name != "nt":
                return None
            return stripped
        return stripped.replace("\\", "/")

    def is_path_in_workspace(self, file_path: str) -> bool:
        """Validates that a resolved path resides strictly inside the workspace repository root."""
        prepared = self._prepare_workspace_path(file_path)
        if prepared is None:
            return False
        abs_path = os.path.abspath(os.path.join(self.repo_path, prepared))
        return self._is_path_safe(abs_path)

    def is_path_under_allowed_directory(self, file_path: str) -> bool:
        """Validates that a resolved path resides strictly inside the allowed directory for reading."""
        prepared = self._prepare_workspace_path(file_path)
        if prepared is None:
            return False
        abs_path = os.path.abspath(os.path.join(self.repo_path, prepared))
        if not self._is_path_safe(abs_path):
            return False
        try:
            real_allowed = os.path.realpath(self.abs_allowed_directory)
            real_path = os.path.realpath(abs_path)
            common = os.path.commonpath([real_allowed, real_path])
            return common == real_allowed
        except Exception:
            return False

    @abc.abstractmethod
    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        """Subclasses must implement this to return the system instructions."""
        pass

    @abc.abstractmethod
    def _build_prompt(self, *args: Any, **kwargs: Any) -> str:
        """Subclasses must implement this to return the user prompt."""
        pass

    def run(self, *args: Any, **kwargs: Any) -> str:
        """Consolidated run method implementing the template pattern.
        Constructs instructions and prompt, then invokes model generation.
        """
        system_instruction = self._build_system_instruction(*args, **kwargs)
        prompt = self._build_prompt(*args, **kwargs)
        try:
            return str(self.model_client.generate(prompt, system_instruction))
        except Exception as e:
            raise RuntimeError(f"Agent {self.name} failed during generation: {e}") from e

    def _is_path_safe(self, abs_path: str) -> bool:
        """Validates that a resolved path resides inside the repository root."""
        try:
            real_repo = os.path.realpath(self.repo_path)
            real_path = os.path.realpath(abs_path)
            common = os.path.commonpath([real_repo, real_path])
            return common == real_repo
        except Exception:
            return False

    def list_files(self, repo_path: Optional[str] = None) -> List[str]:
        target_path = os.path.abspath(repo_path) if repo_path else self.abs_allowed_directory
        if not self._is_path_safe(target_path):
            return []

        files_list = []
        for root, dirs, files in os.walk(target_path):
            # Ignore git and hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for file in files:
                if not file.startswith("."):
                    rel_path = os.path.relpath(os.path.join(root, file), self.repo_path)
                    files_list.append(rel_path.replace("\\", "/"))
        return files_list

    def read_file(self, file_path: str) -> str:
        prepared = self._prepare_workspace_path(file_path)
        if prepared is None:
            return f"Error: Path {file_path} escapes repository root {self.repo_path}"
        abs_path = os.path.abspath(os.path.join(self.repo_path, prepared))
        if not self._is_path_safe(abs_path):
            return f"Error: Path {file_path} escapes repository root {self.repo_path}"
        rel_clean = os.path.relpath(abs_path, self.repo_path).replace("\\", "/")
        is_maca_internal = rel_clean == ".maca" or rel_clean.startswith(".maca/")
        if not is_maca_internal and not self.is_path_under_allowed_directory(prepared):
            return f"Error: Path {file_path} is outside allowed directory {self.allowed_directory}"
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

    def write_file(self, file_path: str, content: str) -> str:
        prepared = self._prepare_workspace_path(file_path)
        if prepared is None:
            return f"Error: Path {file_path} escapes repository root {self.repo_path}"
        abs_path = os.path.abspath(os.path.join(self.repo_path, prepared))
        if not self._is_path_safe(abs_path):
            return f"Error: Path {file_path} escapes repository root {self.repo_path}"
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing to {file_path}: {e}"

    def clean_code_content(self, content: str) -> str:
        content = content.strip()
        while True:
            cleaned = False
            if content.startswith("```"):
                first_line_end = content.find(chr(10))
                if first_line_end != -1:
                    line_content = content[:first_line_end].strip()
                    if line_content.startswith("```"):
                        content = content[first_line_end + 1 :].strip()
                        cleaned = True
            if content.endswith("```"):
                content = content[:-3].strip()
                cleaned = True
            if not cleaned:
                break
        return content

    def parse_files(self, response_text: str) -> Dict[str, str]:
        pattern = r"\[FILE:\s*([^\s\]]+)\]\s*(?:\r?\n)*```\w*\s*\r?\n(.*?)\r?\n```"
        matches = re.findall(pattern, response_text, re.DOTALL)

        files = {}
        for filepath, content in matches:
            files[filepath.strip()] = self.clean_code_content(content)
        return files
