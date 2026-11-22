import os
from typing import Any, Dict, List, Optional

from maca.a2a_call_helper import call_agent
from maca.agents.clarifier import ClarifierAgent
from maca.agents.code_completion_verifier import CodeCompletionVerifierAgent
from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent
from maca.agents.planner import PlannerAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent
from maca.agents.task_classifier import TaskClassifierAgent
from maca.display import OrchestratorDisplay
from maca.health import BackendHealthService
from maca.models.router import ModelRouter
from maca.pipeline import WorkflowPipeline
from maca.rich_compat import Console, Prompt
from maca.workspace import WorkspaceManager

__all__ = [
    "ClarifierAgent",
    "CodeCompletionVerifierAgent",
    "ModelRouter",
    "Orchestrator",
    "PlannerAgent",
    "Prompt",
    "ReviewerAgent",
    "SimpleCoderAgent",
    "SpecAgent",
    "SpecCoderAgent",
    "TaskClassifierAgent",
    "WorkflowPipeline",
    "WorkspaceManager",
]

console = Console()


class Orchestrator:
    """Central coordinator agent responsible for routing tasks, managing agent-to-agent

    interactions, and maintaining conversational context.
    """

    def __init__(self, repo_path: str = ".", allowed_directory: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path)
        self.allowed_directory = allowed_directory or "."
        self.workspace = WorkspaceManager(self.repo_path, allowed_directory=self.allowed_directory)
        self.classifier = TaskClassifierAgent()
        self.evaluator = self.classifier  # Backward compatibility alias
        self.conversation_history: List[str] = []
        self.call_agent = call_agent
        self.display = OrchestratorDisplay(console)
        self.pipeline = WorkflowPipeline(self)

    def _is_coder_done(
        self,
        client: Any,
        task_description: str,
        spec: str,
        generated_files: Dict[str, str],
        task_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Validate if the coder has completed all planned steps via CodeCompletionVerifierAgent."""
        verifier = CodeCompletionVerifierAgent(
            client, repo_path=self.repo_path, allowed_directory=self.allowed_directory
        )
        return verifier.validate(task_description, spec, generated_files, task_name=task_name)

    def _is_gemini_online(self) -> bool:
        return BackendHealthService.is_gemini_online()

    def _is_claude_online(self) -> bool:
        return BackendHealthService.is_claude_online()

    def check_backends_status(self, run_handshakes: bool = False) -> Dict[str, str]:
        return BackendHealthService.check_backends_status(run_handshakes=run_handshakes)

    def run_task(self, task_description: str, model_override: Optional[str] = None):
        """Coordinates the multi-agent workflow pipeline for the given coding task."""
        return self.pipeline.execute(task_description, model_override=model_override)
