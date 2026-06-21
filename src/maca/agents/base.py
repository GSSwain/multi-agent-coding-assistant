import os
import re


class BaseAgent:
    def __init__(self, name, model_client):
        self.name = name
        self.model_client = model_client

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement run()")

    # Helper tools available to the orchestrator/agents
    def list_files(self, repo_path):
        files_list = []
        for root, dirs, files in os.walk(repo_path):
            # Ignore git and hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for file in files:
                if not file.startswith("."):
                    rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                    files_list.append(rel_path)
        return files_list

    def read_file(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

    def write_file(self, file_path, content):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing to {file_path}: {e}"

    def clean_code_content(self, content):
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

    def parse_files(self, response_text):
        pattern = r"\[FILE:\s*([^\s\]]+)\]\s*(?:\r?\n)*```\w*\s*\n(.*?)\n```"
        matches = re.findall(pattern, response_text, re.DOTALL)

        files = {}
        for filepath, content in matches:
            files[filepath.strip()] = self.clean_code_content(content)
        return files
