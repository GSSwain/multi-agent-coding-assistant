import sys
from typing import Any, Dict, Optional

from maca.context import TaskContext
from maca.history_compactor import compact_conversation_history


def _is_mock(obj: Any) -> bool:
    """Helper to detect if a class or function has been patched with unittest.mock."""
    return (
        hasattr(obj, "_mock_return_value")
        or hasattr(obj, "mock_calls")
        or hasattr(obj, "return_value")
        or "mock" in type(obj).__name__.lower()
    )


def _get_orch_attr(attr_name: str, fallback: Any) -> Any:
    """Retrieves an attribute from maca.orchestrator module (respecting mock.patch),

    falling back to standard import if not patched.
    """
    orch_mod = sys.modules.get("maca.orchestrator")
    if orch_mod and hasattr(orch_mod, attr_name):
        return getattr(orch_mod, attr_name)
    return fallback


def build_agent_payload(
    orch: Any, task_context: TaskContext, model_name: str, **kwargs: Any
) -> Dict[str, Any]:
    """Constructs canonical payload for A2A IPC calls via orchestrator.

    When ``plan``, ``spec``, or ``plan_or_spec`` are explicitly provided in
    ``kwargs``, ``task_context.to_compact_dict(...)`` is used so large plan or
    spec bodies are not duplicated inside ``payload["context"]``.
    """
    raw_history = getattr(orch, "conversation_history", [])
    history_payload: Any
    if isinstance(raw_history, (list, tuple)):
        compacted_history, summary = compact_conversation_history(raw_history)
        if summary:
            task_context.history_summary = summary
        history_payload = compacted_history
    else:
        history_payload = raw_history

    has_plan_or_spec = bool(kwargs.get("plan_or_spec"))
    omit_plan = bool(kwargs.get("plan")) or has_plan_or_spec
    omit_spec = bool(kwargs.get("spec")) or has_plan_or_spec
    context_dict = task_context.to_compact_dict(omit_plan=omit_plan, omit_spec=omit_spec)
    payload: Dict[str, Any] = {
        "task_name": task_context.task_name,
        "task_description": task_context.task,
        "history": history_payload,
        "model_name": model_name,
        "repo_path": orch.repo_path,
        "allowed_directory": orch.allowed_directory,
        "context": context_dict,
    }
    payload.update(kwargs)
    return payload


def record_step_progress(
    orch: Any,
    task_context: TaskContext,
    agent_name: str,
    stage: str,
    status: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
) -> None:
    """Synchronizes step completion with task_context and workspace metadata."""
    task_context.refresh_todo_status()
    task_context.update_agent(
        agent_name,
        completed=(status in ("COMPLETED", "APPROVED", "SKIPPED_FOR_SIMPLE")),
        summary=summary,
        details=details or {},
    )
    progress_data: Dict[str, Any] = {"status": status, "context": task_context.to_dict()}
    if file_path:
        progress_data["file"] = file_path
    if details:
        progress_data.update(details)
    orch.workspace.record_task_progress(
        task_context.task_name,
        stage,
        progress_data,
        task_description=task_context.task,
    )
