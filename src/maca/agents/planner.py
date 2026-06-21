from maca.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    def __init__(self, model_client):
        super().__init__("Planner", model_client)

    def run(self, task_description, repo_files=None, history=None):
        files_str = "\n".join(repo_files) if repo_files else "Empty repository"

        history_str = ""
        if history:
            history_str = "\n\nPrevious Conversation History:\n" + "\n".join(history)

        system_instruction = (
            "You are a technical Planner Agent. Your job is to analyze the user request "
            "and create a structured markdown implementation plan. "
            "Do NOT write any code implementation or scripts. Only write the steps and "
            "identify which files need to be created or modified."
        )

        prompt = (
            f"User Task: {task_description}{history_str}\n\n"
            f"Current Files in Repository:\n{files_str}\n\n"
            "Please output a detailed implementation plan in markdown format. "
            "Clearly indicate the files to be created or modified using [NEW] and [MODIFY] tags."
        )

        return self.model_client.generate(prompt, system_instruction)
