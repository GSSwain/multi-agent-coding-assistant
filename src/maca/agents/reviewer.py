from maca.agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    def __init__(self, model_client):
        super().__init__("Reviewer", model_client)

    def run(self, task_description, generated_files, history=None):
        system_instruction = self._build_system_instruction()
        prompt = self._build_prompt(task_description, generated_files, history)
        return self.model_client.generate(prompt, system_instruction)

    def _build_system_instruction(self):
        return (
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

    def _build_prompt(self, task_description, generated_files, history):
        history_context = self._format_history(history)
        files_context = self._format_files_context(generated_files)

        return (
            f"User Task: {task_description}{history_context}\n\n"
            f"Generated Files to Review:\n{files_context}"
            "Please review the code, suggest improvements, and output corrected files if needed."
        )

    def _format_history(self, history):
        if not history:
            return ""
        return "\n\nPrevious Conversation History:\n" + "\n".join(history)

    def _format_files_context(self, files):
        if not files:
            return ""

        formatted_files = ""
        for filepath, content in files.items():
            formatted_files += f"--- FILE: {filepath} ---\n{content}\n\n"
        return formatted_files
