import re
from maca.agents.base import BaseAgent

class ReviewerAgent(BaseAgent):
    def __init__(self, model_client):
        super().__init__("Reviewer", model_client)

    def run(self, task_description, generated_files, history=None):
        files_str = ""
        for filepath, content in generated_files.items():
            files_str += f"--- FILE: {filepath} ---\n{content}\n\n"

        history_str = ""
        if history:
            history_str = "\n\nPrevious Conversation History:\n" + "\n".join(history)

        system_instruction = (
            "You are a Senior Reviewer Agent. Your job is to review the code generated for the task. "
            "Look for syntax errors, logical bugs, missing imports, or edge cases. "
            "If changes are needed, explain why and output the corrected files.\n\n"
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

        prompt = (
            f"User Task: {task_description}{history_str}\n\n"
            f"Generated Files to Review:\n{files_str}"
            "Please review the code, suggest improvements, and output corrected files if needed."
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
