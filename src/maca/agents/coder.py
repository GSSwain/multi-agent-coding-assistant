import re
from maca.agents.base import BaseAgent

class CoderAgent(BaseAgent):
    def __init__(self, name, model_client):
        super().__init__(name, model_client)

    def run(self, task_description, plan, repo_files_content=None, history=None):
        system_instruction = self._build_system_instruction()
        prompt = self._build_prompt(task_description, plan, repo_files_content, history)
        return self.model_client.generate(prompt, system_instruction)

    def _build_system_instruction(self):
        return (
            "You are a Software Coder Agent. Your job is to implement the changes outlined in the plan.\n\n"
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

    def _build_prompt(self, task_description, plan, repo_files_content, history):
        history_context = self._format_history(history)
        files_context = self._format_files_context(repo_files_content)
        
        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Implementation Plan:\n{plan}\n"
            f"{files_context}\n"
            "Please implement the changes and output the files using the requested [FILE: path] format."
        )

    def _format_history(self, history):
        if not history:
            return ""
        return "\n\nPrevious Conversation History:\n" + "\n".join(history)

    def _format_files_context(self, repo_files_content):
        if not repo_files_content:
            return ""
        
        formatted_files = "\n\nExisting File Contents:\n"
        for filepath, content in repo_files_content.items():
            formatted_files += f"--- FILE: {filepath} ---\n{content}\n\n"
        return formatted_files
