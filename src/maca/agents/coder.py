import re
from maca.agents.base import BaseAgent

class CoderAgent(BaseAgent):
    def __init__(self, name, model_client):
        super().__init__(name, model_client)

    def run(self, task_description, plan, repo_files_content=None, history=None):
        files_context = ""
        if repo_files_content:
            files_context = "\n\nExisting File Contents:\n"
            for filepath, content in repo_files_content.items():
                files_context += f"--- FILE: {filepath} ---\n{content}\n\n"

        history_str = ""
        if history:
            history_str = "\n\nPrevious Conversation History:\n" + "\n".join(history)

        system_instruction = (
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

        prompt = (
            f"User Task: {task_description}{history_str}\n\n"
            f"Implementation Plan:\n{plan}\n"
            f"{files_context}\n"
            "Please implement the changes and output the files using the requested [FILE: path] format."
        )

        response = self.model_client.generate(prompt, system_instruction)
        return response

    def parse_files(self, response_text):
        pattern = r"\[FILE:\s*([^\s\]]+)\]\s*(?:\r?\n)*```\w*\s*\n(.*?)\n```"
        matches = re.findall(pattern, response_text, re.DOTALL)
        
        files = {}
        for filepath, content in matches:
            files[filepath.strip()] = self.clean_code_content(content)
        return files
