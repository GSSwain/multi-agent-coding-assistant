import os
from typing import Any, Callable, Dict, Optional, Tuple

from maca import maca_config as config
from maca.agents.reviewer import ReviewerAgent
from maca.context import TaskContext
from maca.delta_context import build_delta_file_context
from maca.rich_compat import Console
from maca.stages.common import (
    _get_orch_attr,
    _is_mock,
    build_agent_payload,
    record_step_progress,
)
from maca.stages.nudge import NudgeLoopRunner

console = Console()


class ReviewStage:
    """Manages pre-review disk persistence, reviewer audit execution,

    and the revision nudge loop.
    """

    def __init__(self, orchestrator: Any):
        self.orch = orchestrator

    def persist_pre_review(
        self,
        generated_files: Dict[str, str],
        file_blocks: Dict[str, Any],
        task_context: TaskContext,
    ) -> None:
        self.orch.display.show_step_header(
            "Step 2.5: Staging generated code changes in .maca/<task>/staging before review..."
        )

        _, summary_records = self.orch.workspace.flush_to_staging(
            task_context.task_name, generated_files
        )

        staging_dir = self.orch.workspace.get_staging_dir(task_context.task_name)
        try:
            rel_staging_dir = os.path.relpath(staging_dir, self.orch.repo_path)
        except ValueError:
            rel_staging_dir = staging_dir

        self.orch.display.show_pre_review_files(
            summary_records, generated_files, config.SANDBOX_READ_ONLY
        )

        self.orch.workspace.record_task_progress(
            task_context.task_name,
            "code_staged",
            {
                "status": "STAGED",
                "staging_dir": rel_staging_dir,
                "files": list(generated_files.keys()),
                "file_blocks_summary": {
                    fp: [
                        f"Lines {b['start_line']}-{b['end_line']} ({b.get('tag', 'modified')})"
                        for b in blks
                    ]
                    for fp, blks in file_blocks.items()
                },
                "context": task_context.to_dict(),
            },
            task_description=task_context.task,
        )

    def run_reviewer_step(
        self,
        client: Any,
        task_description: str,
        spec: str,
        generated_files: Dict[str, str],
        file_blocks: Dict[str, Any],
        model_name: str,
        task_context: TaskContext,
    ) -> Tuple[str, bool, Dict[str, str]]:
        reviewer_cls = _get_orch_attr("ReviewerAgent", ReviewerAgent)
        if _is_mock(reviewer_cls):
            reviewer = reviewer_cls(
                client, repo_path=self.orch.repo_path, allowed_directory=self.orch.allowed_directory
            )
            reviewer_response = reviewer.run(
                task_description,
                generated_files,
                history=self.orch.conversation_history,
                plan_or_spec=spec,
                file_blocks=file_blocks,
                task_name=task_context.task_name,
            )
            is_approved = reviewer.is_approved(reviewer_response)
            reviewed_files = reviewer.parse_files(reviewer_response)
        else:
            payload = build_agent_payload(
                self.orch,
                task_context,
                model_name,
                generated_files=generated_files,
                file_blocks=file_blocks,
                plan_or_spec=spec,
            )
            reviewer_result = self.orch.call_agent("maca.agents.reviewer", payload)
            reviewer_response = reviewer_result.get("result", "")
            is_approved = reviewer_result.get("approved", False)
            reviewed_files = reviewer_result.get("files", {})

        return reviewer_response, is_approved, reviewed_files

    def reviewer_loop(
        self,
        client: Any,
        task_description: str,
        plan: str,
        spec: str,
        generated_files: Dict[str, str],
        file_blocks: Dict[str, Any],
        repo_files_content: Dict[str, str],
        coder_type: str,
        model_name: str,
        task_context: TaskContext,
        run_coder_fn: Optional[Callable[..., Tuple[Dict[str, str], Any, str]]] = None,
        apply_coder_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> Tuple[bool, Dict[str, str]]:
        self.orch.display.show_step_header(
            "Step 3: Reviewer Agent starting...",
            subtitle="Reviewing modified file and line blocks...",
        )

        max_review_attempts = 10
        is_approved = False
        reviewed_files: Dict[str, str] = {}

        for r_attempt in range(max_review_attempts):
            console.print(
                f"[bold yellow]Running Reviewer Agent (Attempt {r_attempt + 1})...[/bold yellow]"
            )
            with console.status(
                "[bold yellow]Reviewer Agent is auditing the generated code line blocks...",
                spinner="dots",
            ):
                reviewer_response, is_approved, reviewed_files = self.run_reviewer_step(
                    client=client,
                    task_description=task_description,
                    spec=spec,
                    generated_files=generated_files,
                    file_blocks=file_blocks,
                    model_name=model_name,
                    task_context=task_context,
                )

            record_step_progress(
                self.orch,
                task_context,
                "reviewer",
                "review",
                "APPROVED" if is_approved else "REVIEWED",
                "Approved" if is_approved else "Revisions requested",
                details={
                    "approved": is_approved,
                    "reviewed_files": list(reviewed_files.keys()) if reviewed_files else [],
                },
            )

            self.orch.display.show_review_report(reviewer_response, r_attempt + 1)

            if is_approved:
                if reviewed_files:
                    for fp, content in reviewed_files.items():
                        generated_files[fp] = content
                    self.orch.workspace.flush_to_staging(task_context.task_name, reviewed_files)
                console.print("[bold green]Reviewer APPROVED the implementation![/bold green]")
                break

            if r_attempt == max_review_attempts - 1:
                console.print(
                    "[bold red]Reached maximum review attempts. Proceeding with current code.[/bold red]"
                )
                if reviewed_files:
                    for fp, content in reviewed_files.items():
                        generated_files[fp] = content
                    self.orch.workspace.flush_to_staging(task_context.task_name, reviewed_files)
                break

            nudge_prompt = (
                f"The Reviewer has audited your code and raised issues / corrections. "
                f"Here is the Reviewer's report:\n\n"
                f"{reviewer_response}\n\n"
                f"Please address all these issues and output the complete updated files."
            )
            if run_coder_fn and apply_coder_update_fn:
                delta_files = build_delta_file_context(
                    repo_files_content,
                    generated_files,
                    reviewer_response,
                )
                updated_blocks = NudgeLoopRunner.run_nudge_iteration(
                    run_coder_fn=run_coder_fn,
                    apply_update_fn=lambda updated_files, summary_label, persist_changes: (
                        apply_coder_update_fn(
                            updated_files=updated_files,
                            generated_files=generated_files,
                            repo_files_content=repo_files_content,
                            task_context=task_context,
                            summary_label=summary_label,
                            persist_changes=persist_changes,
                        )
                    ),
                    nudge_prompt=nudge_prompt,
                    nudge_label="address Reviewer concerns",
                    spinner_message="Coder Agent is applying corrections...",
                    persist_changes=False,
                    coder_type=coder_type,
                    task_description=task_description,
                    plan=plan,
                    spec=spec,
                    repo_files_content=delta_files,
                    client=client,
                    model_name=model_name,
                    task_context=task_context,
                )
                if updated_blocks:
                    file_blocks = updated_blocks

        return is_approved, reviewed_files
