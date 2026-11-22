import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from maca import maca_config as config


def _format_utc_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TaskStore:
    """Persists timestamped task history per working directory under `.maca/tasks.json`."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.maca_dir = os.path.join(self.repo_path, ".maca")
        self.store_path = os.path.join(self.maca_dir, "tasks.json")
        self._memory_tasks: List[Dict[str, Any]] = []

    def _read_disk_tasks(self) -> Optional[List[Dict[str, Any]]]:
        if not os.path.exists(self.store_path):
            return None
        try:
            with open(self.store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception:
            return None
        return None

    def _write_disk_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        if config.SANDBOX_READ_ONLY:
            return
        try:
            os.makedirs(self.maca_dir, exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as handle:
                json.dump(tasks, handle, indent=2)
        except OSError:
            pass

    def load_tasks(self) -> List[Dict[str, Any]]:
        """Return tasks for this working directory ordered newest-first by `updated_at_ts`."""
        disk_tasks = self._read_disk_tasks()
        tasks = disk_tasks if disk_tasks is not None else list(self._memory_tasks)
        self._memory_tasks = list(tasks)
        return sorted(tasks, key=lambda item: float(item.get("updated_at_ts", 0.0)), reverse=True)

    def create_task(
        self,
        task_description: str,
        task_name: Optional[str] = None,
        complexity: Optional[str] = None,
        model_override: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create and persist a new task record in this working directory."""
        ts = float(now_ts if now_ts is not None else time.time())
        iso_ts = _format_utc_timestamp(ts)
        record: Dict[str, Any] = {
            "task_id": uuid.uuid4().hex[:12],
            "task_name": task_name,
            "task_description": task_description,
            "repo_path": self.repo_path,
            "complexity": complexity,
            "model_override": model_override,
            "bootstrap_config": None,
            "status": "in_progress",
            "stage": "started",
            "plan_file": None,
            "spec_file": None,
            "generated_files": [],
            "created_at": iso_ts,
            "updated_at": iso_ts,
            "updated_at_ts": ts,
        }
        tasks = self.load_tasks()
        tasks.insert(0, record)
        self._memory_tasks = tasks
        self._write_disk_tasks(tasks)
        return record

    def update_task(
        self,
        task_id: str,
        now_ts: Optional[float] = None,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """Update fields and timestamp on an existing task record."""
        tasks = self.load_tasks()
        ts = float(now_ts if now_ts is not None else time.time())
        iso_ts = _format_utc_timestamp(ts)
        updated_record: Optional[Dict[str, Any]] = None

        for item in tasks:
            if item.get("task_id") == task_id:
                item.update(updates)
                item["updated_at"] = iso_ts
                item["updated_at_ts"] = ts
                updated_record = item
                break

        if updated_record is not None:
            tasks.sort(key=lambda item: float(item.get("updated_at_ts", 0.0)), reverse=True)
            self._memory_tasks = tasks
            self._write_disk_tasks(tasks)

        return updated_record

    def get_recent_candidates(self, window_minutes: Optional[float] = None) -> List[Dict[str, Any]]:
        """Return the most recent task(s) within `window_minutes` of the latest task."""
        tasks = self.load_tasks()
        if not tasks:
            return []

        effective_window = (
            window_minutes if window_minutes is not None else config.CONTINUE_RECENT_WINDOW_MINUTES
        )
        window_seconds = max(0.0, float(effective_window) * 60.0)
        latest_ts = float(tasks[0].get("updated_at_ts", 0.0))

        return [
            task
            for task in tasks
            if (latest_ts - float(task.get("updated_at_ts", 0.0))) <= window_seconds
        ]
