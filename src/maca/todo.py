import os
import re
from typing import Any, Dict, List, Optional


def get_todo_path(repo_path: str, task_name: str, agent_name: str) -> str:
    """Returns the path to the agent's .todo file: .maca/<task>/<agent>.todo."""
    safe_task = "".join(c if c.isalnum() else "-" for c in task_name[:30]).strip("-").lower()
    if not safe_task:
        safe_task = "default"
    return os.path.join(os.path.abspath(repo_path), ".maca", safe_task, f"{agent_name}.todo")


def parse_plan_to_items(plan_text: str) -> List[str]:
    """Extract individual actionable steps from a markdown plan or specification."""
    items = []
    lines = plan_text.strip().splitlines()

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        # Match numbered lists (1. ...), bullets (- ..., * ...), or checkboxes (- [ ] ...)
        match = re.match(r"^(\d+\.|\-|\*)\s+(?:\[[ xX]\]\s*)?(.*)", line_clean)
        if match:
            text = match.group(2).strip()
            # Clean leading bold or tags if present
            if text and not text.startswith("---"):
                items.append(text)

    if not items:
        # Fallback if text doesn't contain structured bullet/number items
        items = ["Implement planned task steps."]

    return items


def init_todo_file(
    repo_path: str,
    task_name: str,
    agent_name: str,
    plan_text: str,
) -> str:
    """Initialize the .maca/<task>-<agent>.todo file if it doesn't already exist.

    Returns the todo content.
    """
    todo_path = get_todo_path(repo_path, task_name, agent_name)

    if os.path.exists(todo_path):
        try:
            with open(todo_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass

    items = parse_plan_to_items(plan_text)
    lines = [f"# Todo Progress for task: {task_name} ({agent_name})", ""]
    for item in items:
        lines.append(f"- [ ] {item}")

    content = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(todo_path), exist_ok=True)
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content


def read_todo_file(repo_path: str, task_name: str, agent_name: str) -> Optional[str]:
    """Read the .todo file if present."""
    todo_path = get_todo_path(repo_path, task_name, agent_name)
    if os.path.exists(todo_path):
        try:
            with open(todo_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    # Backward compatibility fallback to legacy .maca/<task>-<agent>.todo
    safe_task = "".join(c if c.isalnum() else "-" for c in task_name[:30]).strip("-").lower()
    legacy_path = os.path.join(
        os.path.abspath(repo_path), ".maca", f"{safe_task}-{agent_name}.todo"
    )
    if os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def write_todo_file(repo_path: str, task_name: str, agent_name: str, content: str) -> str:
    """Write or overwrite the .todo file."""
    todo_path = get_todo_path(repo_path, task_name, agent_name)
    os.makedirs(os.path.dirname(todo_path), exist_ok=True)
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write(content)
    return todo_path


def update_todo_progress(
    repo_path: str,
    task_name: str,
    agent_name: str,
    generated_files: Optional[Dict[str, str]] = None,
    is_complete: bool = False,
    nudge_feedback: Optional[str] = None,
) -> str:
    """Update existing todo items marking them complete ([x]) or appending nudge feedback.

    Returns the updated todo string.
    """
    content = read_todo_file(repo_path, task_name, agent_name)

    if not content:
        content = f"# Todo Progress for task: {task_name} ({agent_name})\n- [ ] Task in progress\n"

    lines = content.splitlines()
    updated_lines = []

    file_keys = [f.lower().strip() for f in (generated_files or {}).keys()]

    for line in lines:
        if line.strip().startswith("- [ ]"):
            item_text = line.replace("- [ ]", "").strip()

            should_mark_done = False
            if is_complete:
                should_mark_done = True
            elif file_keys:
                # If this todo item references any of the generated files
                for fk in file_keys:
                    basename = os.path.basename(fk)
                    if fk in item_text.lower() or basename in item_text.lower():
                        should_mark_done = True
                        break

            if should_mark_done:
                updated_lines.append(f"- [x] {item_text}")
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    # If there is specific nudge feedback and not marked complete, add it as a pending item if not already there
    if nudge_feedback and not is_complete:
        feedback_summary = nudge_feedback.strip().splitlines()[0][:80]
        feedback_item = f"- [ ] Nudge requirement: {feedback_summary}"
        if (
            feedback_item not in updated_lines
            and f"- [x] Nudge requirement: {feedback_summary}" not in updated_lines
        ):
            updated_lines.append(feedback_item)

    new_content = "\n".join(updated_lines) + "\n"
    write_todo_file(repo_path, task_name, agent_name, new_content)
    return new_content


def get_all_todo_statuses(repo_path: str, task_name: str) -> Dict[str, Any]:
    """Retrieve structured todo status for all agents for the given task."""
    agents = ["planner", "spec", "coder", "code_completion_verifier", "reviewer"]
    statuses: Dict[str, Any] = {}

    for agent in agents:
        content = read_todo_file(repo_path, task_name, agent)
        if not content:
            statuses[agent] = {
                "exists": False,
                "status": "NOT_STARTED",
                "completed_count": 0,
                "pending_count": 0,
                "completed_items": [],
                "pending_items": [],
            }
            continue

        lines = content.splitlines()
        completed = [
            line.replace("- [x]", "").strip() for line in lines if line.strip().startswith("- [x]")
        ]
        pending = [
            line.replace("- [ ]", "").strip() for line in lines if line.strip().startswith("- [ ]")
        ]

        status_label = "IN_PROGRESS"
        if completed and not pending:
            status_label = "COMPLETED"
        elif not completed and not pending:
            status_label = "NOT_STARTED"

        statuses[agent] = {
            "exists": True,
            "status": status_label,
            "completed_count": len(completed),
            "pending_count": len(pending),
            "completed_items": completed,
            "pending_items": pending,
        }

    return statuses
