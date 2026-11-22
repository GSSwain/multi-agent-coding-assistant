import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from maca.todo import get_all_todo_statuses


@dataclass
class TaskContext:
    """Structured context object encapsulating task state, repository boundaries,

    planning metadata, per-agent todo status, and agent completion updates.
    """

    task: str
    task_name: str
    repo_path: str
    allowed_directory: str = "."
    complexity: str = "SIMPLE"
    plan: Optional[str] = None
    spec: Optional[str] = None
    todo_status: Dict[str, Any] = field(default_factory=dict)
    agent_updates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    bootstrap_config: Dict[str, str] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )

    @property
    def abs_allowed_directory(self) -> str:
        """Returns the absolute path of the allowed directory."""
        if os.path.isabs(self.allowed_directory):
            return os.path.abspath(self.allowed_directory)
        return os.path.abspath(os.path.join(self.repo_path, self.allowed_directory))

    def is_path_under_allowed_directory(self, file_path: str) -> bool:
        """Validates that a resolved path resides strictly inside the allowed directory for reading."""
        abs_path = os.path.abspath(os.path.join(self.repo_path, file_path))
        try:
            allowed_dir = self.abs_allowed_directory
            common = os.path.commonpath([allowed_dir, abs_path])
            return common == allowed_dir
        except Exception:
            return False

    def is_path_in_workspace(self, file_path: str) -> bool:
        """Validates that a resolved path resides strictly inside the workspace repository root."""
        abs_path = os.path.abspath(os.path.join(self.repo_path, file_path))
        try:
            repo_root = os.path.abspath(self.repo_path)
            common = os.path.commonpath([repo_root, abs_path])
            return common == repo_root
        except Exception:
            return False

    def update_agent(
        self,
        agent: str,
        completed: bool,
        summary: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an update from an agent indicating completion and execution details."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.agent_updates[agent] = {
            "agent": agent,
            "completed": completed,
            "summary": summary,
            "timestamp": now,
            "details": details or {},
        }
        self.updated_at = now

    def refresh_todo_status(self) -> Dict[str, Any]:
        """Refresh the per-agent todo status from disk."""
        self.todo_status = get_all_todo_statuses(self.repo_path, self.task_name)
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return self.todo_status

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to a structured dictionary."""
        return {
            "task": self.task,
            "task_name": self.task_name,
            "complexity": self.complexity,
            "repo_path": self.repo_path,
            "allowed_directory": self.allowed_directory,
            "plan": self.plan,
            "spec": self.spec,
            "todo_status": self.todo_status,
            "agent_updates": self.agent_updates,
            "bootstrap_config": self.bootstrap_config,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContext":
        """Deserialize context from a dictionary."""
        return cls(
            task=data.get("task", ""),
            task_name=data.get("task_name", ""),
            repo_path=data.get("repo_path", "."),
            allowed_directory=data.get("allowed_directory", data.get("allowed_dir", ".")),
            complexity=data.get("complexity", "SIMPLE"),
            plan=data.get("plan"),
            spec=data.get("spec"),
            todo_status=data.get("todo_status", {}),
            agent_updates=data.get("agent_updates", {}),
            bootstrap_config=data.get("bootstrap_config", {}),
            updated_at=data.get("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )

    def format_summary(self) -> str:
        """Format a human-readable multi-line summary of current context."""
        lines = [
            f"=== Task Context: {self.task_name} ===",
            f"Task: {self.task}",
            f"Complexity: {self.complexity}",
            f"Workspace (Modifiable): {self.repo_path}",
            f"Allowed Directory (Read-Only): {self.allowed_directory}",
            f"Plan Available: {'Yes' if self.plan else 'No'}",
            f"Spec Available: {'Yes' if self.spec else 'No'}",
            "",
            "Agent Completion Status:",
        ]
        for ag, up in self.agent_updates.items():
            comp_flag = "COMPLETED" if up.get("completed") else "IN_PROGRESS"
            lines.append(f" - [{ag}]: {comp_flag} - {up.get('summary', '')}")

        lines.append("")
        lines.append("Todo Status Across Agents:")
        for ag, st in self.todo_status.items():
            lines.append(
                f" - [{ag}]: {st.get('status', 'NOT_STARTED')} "
                f"({st.get('completed_count', 0)} completed, {st.get('pending_count', 0)} pending)"
            )

        return "\n".join(lines)
