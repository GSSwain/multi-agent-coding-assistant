import difflib
import hashlib
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple


class WorkspaceManager:
    """Manages workspace file interactions, repository exploration, diff line block tracking,

    progress metadata under .maca, and sandbox safety.
    """

    def __init__(self, repo_path: str = ".", allowed_directory: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path)
        self.maca_dir = os.path.join(self.repo_path, ".maca")
        self.allowed_directory = allowed_directory or "."

    @staticmethod
    def generate_task_slug(task_description: str) -> str:
        """Generate a safe, collision-resistant task directory slug (max 30 chars).

        For short task names (<= 24 chars), returns the clean alphanumeric slug directly.
        For longer descriptions, appends a 6-character SHA-256 hash suffix to prevent
        truncation collisions across tasks that share the same prefix.
        """
        raw_slug = "".join(c if c.isalnum() else "-" for c in task_description).strip("-").lower()
        while "--" in raw_slug:
            raw_slug = raw_slug.replace("--", "-")
        if not raw_slug:
            return "default"
        if len(task_description) <= 24 and len(raw_slug) <= 24:
            return raw_slug
        task_hash = hashlib.sha256(task_description.encode("utf-8")).hexdigest()[:6]
        prefix = raw_slug[:23].rstrip("-")
        return f"{prefix}-{task_hash}"

    @property
    def abs_allowed_directory(self) -> str:
        """Returns the absolute path of the allowed directory."""
        if os.path.isabs(self.allowed_directory):
            return os.path.abspath(self.allowed_directory)
        return os.path.abspath(os.path.join(self.repo_path, self.allowed_directory))

    def is_path_safe(self, abs_path: str) -> bool:
        """Validates that a resolved path resides strictly inside the repository root."""
        try:
            real_repo = os.path.realpath(self.repo_path)
            real_path = os.path.realpath(abs_path)
            common = os.path.commonpath([real_repo, real_path])
            return common == real_repo
        except Exception:
            return False

    def is_path_under_allowed_directory(self, rel_path: str) -> bool:
        """Validates that a path resides strictly inside the allowed directory."""
        abs_path = os.path.abspath(os.path.join(self.repo_path, rel_path))
        if not self.is_path_safe(abs_path):
            return False
        try:
            real_allowed = os.path.realpath(self.abs_allowed_directory)
            real_path = os.path.realpath(abs_path)
            common = os.path.commonpath([real_allowed, real_path])
            return common == real_allowed
        except Exception:
            return False

    def list_files(self, target_path: Optional[str] = None) -> List[str]:
        """List all non-hidden, non-ignored files in the repository under allowed_directory."""
        base_dir = os.path.abspath(target_path) if target_path else self.abs_allowed_directory
        if not self.is_path_safe(base_dir):
            return []

        files_list = []
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for file in files:
                if not file.startswith("."):
                    rel_path = os.path.relpath(os.path.join(root, file), self.repo_path)
                    files_list.append(rel_path)
        return files_list

    def read_file(self, rel_path: str) -> str:
        """Read file contents safely within workspace and allowed_directory bounds."""
        abs_path = os.path.abspath(os.path.join(self.repo_path, rel_path))
        if not self.is_path_safe(abs_path):
            return f"Error: Path {rel_path} escapes repository root {self.repo_path}"
        clean_rel = os.path.relpath(abs_path, self.repo_path)
        if not clean_rel.startswith(".maca") and not self.is_path_under_allowed_directory(rel_path):
            return f"Error: Path {rel_path} is outside allowed directory {self.allowed_directory}"
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {rel_path}: {e}"

    def write_file(self, rel_path: str, content: str) -> str:
        """Write file contents safely within the workspace."""
        abs_path = os.path.abspath(os.path.join(self.repo_path, rel_path))
        if not self.is_path_safe(abs_path):
            return f"Error: Path {rel_path} escapes repository root {self.repo_path}"
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {rel_path}"
        except Exception as e:
            return f"Error writing to {rel_path}: {e}"

    def compute_file_blocks(
        self, files: Dict[str, str], existing_contents: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Compute the file and line blocks modified or added in each file."""
        file_blocks: Dict[str, List[Dict[str, Any]]] = {}

        for rel_path, new_content in files.items():
            clean_rel_path = rel_path.strip().lstrip("/")
            new_lines = new_content.splitlines(keepends=True)

            old_content = ""
            if existing_contents and clean_rel_path in existing_contents:
                old_content = existing_contents[clean_rel_path]
            else:
                existing = self.read_file(clean_rel_path)
                if not existing.startswith("Error"):
                    old_content = existing

            if not old_content:
                # Completely new file
                file_blocks[clean_rel_path] = [
                    {
                        "start_line": 1,
                        "end_line": max(1, len(new_lines)),
                        "tag": "created",
                        "code": new_content,
                    }
                ]
            else:
                old_lines = old_content.splitlines(keepends=True)
                matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
                blocks: List[Dict[str, Any]] = []

                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag != "equal":
                        start_line = j1 + 1
                        end_line = max(j1 + 1, j2)
                        code_snippet = "".join(new_lines[j1:j2])
                        blocks.append(
                            {
                                "start_line": start_line,
                                "end_line": end_line,
                                "tag": tag,
                                "code": code_snippet,
                            }
                        )

                if not blocks:
                    blocks = [
                        {
                            "start_line": 1,
                            "end_line": max(1, len(new_lines)),
                            "tag": "full",
                            "code": new_content,
                        }
                    ]

                file_blocks[clean_rel_path] = blocks

        return file_blocks

    def apply_changes(
        self, generated_files: Dict[str, str], sandbox_read_only: bool = False
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Apply a batch of generated files to disk, enforcing sandbox safety.

        Returns (written_count, summary_records).
        """
        summary_records = []
        written_count = 0

        for rel_path, content in generated_files.items():
            clean_rel_path = rel_path.strip().lstrip("/")
            abs_path = os.path.abspath(os.path.join(self.repo_path, clean_rel_path))

            if not self.is_path_safe(abs_path):
                summary_records.append(
                    {
                        "path": rel_path,
                        "action": "Failed: Sandbox escape blocked",
                        "size": "0",
                        "safe": False,
                    }
                )
                continue

            action = "Modified" if os.path.exists(abs_path) else "Created"

            if sandbox_read_only:
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": f"{action} (Dry-Run)",
                        "size": str(len(content)),
                        "safe": True,
                    }
                )
                continue

            res = self.write_file(clean_rel_path, content)
            if "Successfully" in res:
                written_count += 1
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": action,
                        "size": str(len(content)),
                        "safe": True,
                    }
                )
            else:
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": f"Failed: {res}",
                        "size": "0",
                        "safe": False,
                    }
                )

        return written_count, summary_records

    def get_staging_dir(self, task_name: str) -> str:
        """Returns the absolute path to the task's staging directory: .maca/<task>/staging."""
        safe_task = (
            "".join(c if c.isalnum() else "-" for c in task_name[:30]).strip("-").lower()
            or "default"
        )
        return os.path.join(self.maca_dir, safe_task, "staging")

    def flush_to_staging(
        self, task_name: str, files: Dict[str, str]
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Flush a batch of generated or updated files to the task's staging directory.

        This checkpoints progress to disk incrementally without touching the main workspace.
        """
        staging_dir = self.get_staging_dir(task_name)
        os.makedirs(staging_dir, exist_ok=True)
        summary_records = []
        written_count = 0

        for rel_path, content in files.items():
            clean_rel_path = rel_path.strip().lstrip("/")
            abs_staging_path = os.path.abspath(os.path.join(staging_dir, clean_rel_path))

            # Validate that staging file cannot escape the staging directory (including symlinks)
            try:
                real_staging = os.path.realpath(staging_dir)
                real_target = os.path.realpath(abs_staging_path)
                common = os.path.commonpath([real_staging, real_target])
                if common != real_staging:
                    summary_records.append(
                        {
                            "path": clean_rel_path,
                            "action": "Failed: Staging escape blocked",
                            "size": "0",
                            "safe": False,
                        }
                    )
                    continue
            except Exception as e:
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": f"Failed: Staging escape blocked ({e})",
                        "size": "0",
                        "safe": False,
                    }
                )
                continue

            try:
                os.makedirs(os.path.dirname(abs_staging_path), exist_ok=True)
                with open(abs_staging_path, "w", encoding="utf-8") as f:
                    f.write(content)
                written_count += 1
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": "Staged",
                        "size": str(len(content)),
                        "safe": True,
                    }
                )
            except Exception as e:
                summary_records.append(
                    {
                        "path": clean_rel_path,
                        "action": f"Failed: {e}",
                        "size": "0",
                        "safe": False,
                    }
                )

        return written_count, summary_records

    def list_staging_files(self, task_name: str) -> List[str]:
        """List all relative file paths currently staged under .maca/<task>/staging."""
        staging_dir = self.get_staging_dir(task_name)
        if not os.path.exists(staging_dir):
            return []

        staged_list = []
        for root, _, files in os.walk(staging_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, staging_dir)
                staged_list.append(rel_path)
        return sorted(staged_list)

    def read_staging_file(self, task_name: str, rel_path: str) -> str:
        """Read a file from the task's staging directory."""
        clean_rel = rel_path.strip().lstrip("/")
        staging_dir = self.get_staging_dir(task_name)
        abs_path = os.path.abspath(os.path.join(staging_dir, clean_rel))
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading staged file {rel_path}: {e}"

    def promote_staging_files(
        self, task_name: str, sandbox_read_only: bool = False, clean_staging: bool = True
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Promote (move) all staged files from .maca/<task>/staging into the real workspace repository.

        Enforces sandbox permissions and safety checks, and removes the temporary staging
        directory after promotion so approved files live in the target directory.
        """
        staging_dir = self.get_staging_dir(task_name)
        if not os.path.exists(staging_dir):
            return 0, []

        staged_files: Dict[str, str] = {}
        for rel_path in self.list_staging_files(task_name):
            content = self.read_staging_file(task_name, rel_path)
            if not content.startswith("Error reading staged file"):
                staged_files[rel_path] = content

        written_count, records = self.apply_changes(
            staged_files, sandbox_read_only=sandbox_read_only
        )
        if clean_staging and not sandbox_read_only and self.is_path_safe(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        return written_count, records

    def cleanup_tasks(
        self, max_age_days: Optional[float] = None, staging_only: bool = False
    ) -> Tuple[int, List[str]]:
        """Remove old task directories or staging subdirectories under .maca/.

        Returns (removed_count, removed_relative_paths).
        """
        if not os.path.exists(self.maca_dir):
            return 0, []

        cutoff: Optional[float] = None
        if max_age_days is not None:
            cutoff = time.time() - (max_age_days * 86400.0)

        removed_paths: List[str] = []
        for entry in sorted(os.listdir(self.maca_dir)):
            task_dir = os.path.join(self.maca_dir, entry)
            if not os.path.isdir(task_dir) or not self.is_path_safe(task_dir):
                continue

            if cutoff is not None:
                try:
                    mtime = os.path.getmtime(task_dir)
                    if mtime >= cutoff:
                        continue
                except OSError:
                    continue

            target_to_remove = os.path.join(task_dir, "staging") if staging_only else task_dir
            if os.path.exists(target_to_remove) and self.is_path_safe(target_to_remove):
                shutil.rmtree(target_to_remove, ignore_errors=True)
                removed_paths.append(os.path.relpath(target_to_remove, self.repo_path))

        return len(removed_paths), removed_paths

    def record_task_progress(
        self,
        task_id: str,
        stage: str,
        details: Dict[str, Any],
        task_description: str = "",
    ) -> str:
        """Persist structured progress in .maca/<task>/ metadata files."""
        safe_task = "".join(c if c.isalnum() else "-" for c in task_id[:30]).strip("-").lower()
        if not safe_task:
            safe_task = "default"
        task_dir = os.path.join(self.maca_dir, safe_task)
        os.makedirs(task_dir, exist_ok=True)
        meta_file = os.path.join(task_dir, "task.json")
        progress_md_file = os.path.join(task_dir, "progress.md")

        task_data: Dict[str, Any] = {
            "task_id": task_id,
            "task_description": task_description,
            "stages": {},
            "current_stage": stage,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Check new path or legacy flat path
        legacy_meta = os.path.join(self.maca_dir, f"task-{task_id}.json")
        read_meta = (
            meta_file
            if os.path.exists(meta_file)
            else (legacy_meta if os.path.exists(legacy_meta) else None)
        )
        if read_meta:
            try:
                with open(read_meta, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if isinstance(existing_data, dict):
                        task_data["stages"] = existing_data.get("stages", {})
                        if not task_description:
                            task_data["task_description"] = existing_data.get(
                                "task_description", ""
                            )
            except Exception:
                pass

        task_data["stages"][stage] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **details,
        }
        task_data["current_stage"] = stage

        # Write JSON meta file
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, indent=2)

        # Write human-readable progress markdown
        md_lines = [
            f"# Task Progress: {task_data.get('task_description', task_id)}",
            "",
            f"- **Current Stage:** `{stage}`",
            f"- **Last Updated:** {task_data['updated_at']}",
            "",
            "## Stages Overview",
        ]
        for s_name, s_info in task_data["stages"].items():
            status = s_info.get("status", "COMPLETED")
            md_lines.append(f"- **{s_name.upper()}**: `{status}` ({s_info.get('timestamp')})")
            if "files" in s_info:
                md_lines.append(f"  - Files: {', '.join(s_info['files'])}")
            if "file" in s_info:
                md_lines.append(f"  - Document: `{s_info['file']}`")

        with open(progress_md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")

        return meta_file
