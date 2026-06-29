import abc
import os
import re
from typing import Any, Dict, List, Optional


class BaseAgent(abc.ABC):
    def __init__(self, name: str, model_client: Any, repo_path: str = "."):
        self.name = name
        self.model_client = model_client
        self.repo_path = os.path.abspath(repo_path)

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
            common = os.path.commonpath([self.repo_path, abs_path])
            return common == self.repo_path
        except Exception:
            return False

    def list_files(self, repo_path: Optional[str] = None) -> List[str]:
        target_path = os.path.abspath(repo_path) if repo_path else self.repo_path
        if not self._is_path_safe(target_path):
            return []

        files_list = []
        for root, dirs, files in os.walk(target_path):
            # Ignore git and hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for file in files:
                if not file.startswith("."):
                    rel_path = os.path.relpath(os.path.join(root, file), self.repo_path)
                    files_list.append(rel_path)
        return files_list

    def read_file(self, file_path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self.repo_path, file_path))
        if not self._is_path_safe(abs_path):
            return f"Error: Path {file_path} escapes repository root {self.repo_path}"
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

    def write_file(self, file_path: str, content: str) -> str:
        abs_path = os.path.abspath(os.path.join(self.repo_path, file_path))
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
        pattern = r"\[FILE:\s*([^\s\]]+)\]\s*(?:\r?\n)*```\w*\s*\n(.*?)\n```"
        matches = re.findall(pattern, response_text, re.DOTALL)

        files = {}
        for filepath, content in matches:
            files[filepath.strip()] = self.clean_code_content(content)
        return files
