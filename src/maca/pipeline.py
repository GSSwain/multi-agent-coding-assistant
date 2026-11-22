from typing import Any, Dict, List, Optional, Tuple

from maca import maca_config as config
from maca.context import TaskContext
from maca.models.router import ModelRouter
from maca.stages.coding import CodingStage
from maca.stages.common import build_agent_payload, record_step_progress
from maca.stages.planning import PlanningStage
from maca.stages.review import ReviewStage


class WorkflowPipeline:
    """Coordinates execution of multi-agent coding stages:

    Classification -> Planning -> Spec & Approval -> Coding & Verification -> Review.
    """

    def __init__(self, orchestrator: Any):
        self.orch = orchestrator
        self.planning_stage = PlanningStage(orchestrator)
        self.coding_stage = CodingStage(orchestrator)
        self.review_stage = ReviewStage(orchestrator)

    # -------------------------------------------------------------------------
    # Backward-compatible delegate methods
    # -------------------------------------------------------------------------

    def _build_agent_payload(
        self, task_context: TaskContext, model_name: str, **kwargs: Any
    ) -> Dict[str, Any]:
        return build_agent_payload(self.orch, task_context, model_name, **kwargs)

    def _record_step_progress(
        self,
        task_context: TaskContext,
        agent_name: str,
        stage: str,
        status: str,
        summary: str,
        details: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> None:
        record_step_progress(
            self.orch, task_context, agent_name, stage, status, summary, details, file_path
        )

    def _classify_task(self, task_description: str, task_context: TaskContext) -> str:
        return self.planning_stage.classify_task(task_description, task_context)

    def _clarify_task(
        self,
        task_description: str,
        task_context: TaskContext,
        client: Any = None,
        model_name: Optional[str] = None,
        interactive: bool = True,
    ) -> Optional[Dict[str, str]]:
        return self.planning_stage.clarify_task(
            task_description,
            task_context,
            client=client,
            model_name=model_name,
            interactive=interactive,
        )

    def _plan_task(
        self,
        task_description: str,
        task_context: TaskContext,
        client: Any,
        model_name: str,
    ) -> Tuple[str, List[str]]:
        return self.planning_stage.plan_task(task_description, task_context, client, model_name)

    def _spec_task(
        self,
        task_description: str,
        plan: str,
        complexity: str,
        client: Any,
        model_name: str,
        task_context: TaskContext,
    ) -> Optional[str]:
        return self.planning_stage.spec_task(
            task_description, plan, complexity, client, model_name, task_context
        )

    def _collect_repo_files_content(
        self, repo_files: List[str], plan: str, spec: str
    ) -> Dict[str, str]:
        return self.coding_stage.collect_repo_files_content(repo_files, plan, spec)

    def _run_coder_step(
        self,
        coder_type: str,
        task_description: str,
        plan: str,
        spec: str,
        repo_files_content: Dict[str, str],
        client: Any,
        model_name: str,
        task_context: TaskContext,
        nudge: Optional[str] = None,
    ) -> Tuple[Dict[str, str], Dict[str, Any], str]:
        return self.coding_stage.run_coder_step(
            coder_type=coder_type,
            task_description=task_description,
            plan=plan,
            spec=spec,
            repo_files_content=repo_files_content,
            client=client,
            model_name=model_name,
            task_context=task_context,
            nudge=nudge,
        )

    def _apply_coder_update(
        self,
        updated_files: Dict[str, str],
        generated_files: Dict[str, str],
        repo_files_content: Dict[str, str],
        task_context: TaskContext,
        summary_label: str,
        persist_changes: bool = False,
    ) -> Dict[str, Any]:
        return self.coding_stage.apply_coder_update(
            updated_files=updated_files,
            generated_files=generated_files,
            repo_files_content=repo_files_content,
            task_context=task_context,
            summary_label=summary_label,
            persist_changes=persist_changes,
        )

    def _completion_verification_loop(
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
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        return self.coding_stage.completion_verification_loop(
            client=client,
            task_description=task_description,
            plan=plan,
            spec=spec,
            generated_files=generated_files,
            file_blocks=file_blocks,
            repo_files_content=repo_files_content,
            coder_type=coder_type,
            model_name=model_name,
            task_context=task_context,
        )

    def _code_and_verify(
        self,
        task_description: str,
        plan: str,
        spec: str,
        complexity: str,
        repo_files_content: Dict[str, str],
        client: Any,
        model_name: str,
        task_context: TaskContext,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        return self.coding_stage.code_and_verify(
            task_description=task_description,
            plan=plan,
            spec=spec,
            complexity=complexity,
            repo_files_content=repo_files_content,
            client=client,
            model_name=model_name,
            task_context=task_context,
        )

    def _persist_pre_review(
        self,
        generated_files: Dict[str, str],
        file_blocks: Dict[str, Any],
        task_context: TaskContext,
    ) -> None:
        self.review_stage.persist_pre_review(generated_files, file_blocks, task_context)

    def _run_reviewer_step(
        self,
        client: Any,
        task_description: str,
        spec: str,
        generated_files: Dict[str, str],
        file_blocks: Dict[str, Any],
        model_name: str,
        task_context: TaskContext,
    ) -> Tuple[str, bool, Dict[str, str]]:
        return self.review_stage.run_reviewer_step(
            client=client,
            task_description=task_description,
            spec=spec,
            generated_files=generated_files,
            file_blocks=file_blocks,
            model_name=model_name,
            task_context=task_context,
        )

    def _reviewer_loop(
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
    ) -> Tuple[bool, Dict[str, str]]:
        return self.review_stage.reviewer_loop(
            client=client,
            task_description=task_description,
            plan=plan,
            spec=spec,
            generated_files=generated_files,
            file_blocks=file_blocks,
            repo_files_content=repo_files_content,
            coder_type=coder_type,
            model_name=model_name,
            task_context=task_context,
            run_coder_fn=self.coding_stage.run_coder_step,
            apply_coder_update_fn=self.coding_stage.apply_coder_update,
        )

    def _finalize_task(
        self,
        task_description: str,
        plan: str,
        generated_files: Dict[str, str],
        is_approved: bool,
    ) -> None:
        self.orch.display.show_task_completed(is_dry_run=config.SANDBOX_READ_ONLY)
        self.orch.conversation_history.append(f"User Request: {task_description}")
        self.orch.conversation_history.append(f"Planner Implementation Steps:\n{plan}")
        if not is_approved:
            self.orch.conversation_history.append(
                "Reviewer Decision: REVISION_FAILED (Staged in .maca, not applied to repository)"
            )
        elif config.SANDBOX_READ_ONLY:
            self.orch.conversation_history.append(
                "Files Created/Modified (Dry-Run Preview only): "
                + ", ".join(generated_files.keys())
            )
            self.orch.conversation_history.append("Reviewer Decision: APPROVED")
        else:
            files_written = ", ".join(generated_files.keys()) if generated_files else "None"
            self.orch.conversation_history.append(f"Files Modified/Created: {files_written}")
            self.orch.conversation_history.append("Reviewer Decision: APPROVED")

    def execute(self, task_description: str, model_override: Optional[str] = None) -> None:
        self.orch.display.show_task_header(
            task_description, self.orch.repo_path, self.orch.allowed_directory
        )

        safe_task_name = self.orch.workspace.generate_task_slug(task_description)

        task_context = TaskContext(
            task=task_description,
            task_name=safe_task_name,
            repo_path=self.orch.repo_path,
            allowed_directory=self.orch.allowed_directory,
        )

        # 1. Evaluate Complexity
        complexity = self.planning_stage.classify_task(task_description, task_context)

        # 2. Select Model Client
        model_name, client = ModelRouter.select_model(
            complexity=complexity,
            model_override=model_override,
            is_gemini_online_fn=self.orch._is_gemini_online,
            is_claude_online_fn=self.orch._is_claude_online,
        )
        self.orch.display.show_model_selection(model_name, model_override)

        # 2.5 Clarify Framework Bootstrap Parameters (e.g. Maven vs Gradle, Java version)
        self.planning_stage.clarify_task(
            task_description, task_context, client=client, model_name=model_name
        )

        # 3. Planning Step
        plan, repo_files = self.planning_stage.plan_task(
            task_description, task_context, client, model_name
        )

        # 4. Specification Step (with human interactive approval)
        spec = self.planning_stage.spec_task(
            task_description, plan, complexity, client, model_name, task_context
        )
        if spec is None:
            return  # Cancelled by user

        # 5. Coding & Completion Verification Loop
        repo_files_content = self.coding_stage.collect_repo_files_content(repo_files, plan, spec)
        generated_files, file_blocks = self.coding_stage.code_and_verify(
            task_description=task_description,
            plan=plan,
            spec=spec,
            complexity=complexity,
            repo_files_content=repo_files_content,
            client=client,
            model_name=model_name,
            task_context=task_context,
        )

        # 6. Pre-Review Persistence to Disk
        self.review_stage.persist_pre_review(
            generated_files=generated_files,
            file_blocks=file_blocks,
            task_context=task_context,
        )

        # 7. Reviewer Audit Loop
        coder_type = "SIMPLE" if complexity == "SIMPLE" else "SPEC"
        is_approved, reviewed_files = self.review_stage.reviewer_loop(
            client=client,
            task_description=task_description,
            plan=plan,
            spec=spec,
            generated_files=generated_files,
            file_blocks=file_blocks,
            repo_files_content=repo_files_content,
            coder_type=coder_type,
            model_name=model_name,
            task_context=task_context,
            run_coder_fn=self.coding_stage.run_coder_step,
            apply_coder_update_fn=self.coding_stage.apply_coder_update,
        )

        # 8. Promote Staged Files to Workspace upon Approval
        if is_approved:
            if generated_files:
                self.orch.workspace.flush_to_staging(task_context.task_name, generated_files)
            _, promoted_records = self.orch.workspace.promote_staging_files(
                task_context.task_name,
                sandbox_read_only=config.SANDBOX_READ_ONLY,
                clean_staging=True,
            )
            if hasattr(self.orch.display, "show_promoted_files"):
                self.orch.display.show_promoted_files(
                    promoted_records, self.orch.repo_path, config.SANDBOX_READ_ONLY
                )
            self.orch.workspace.record_task_progress(
                task_context.task_name,
                "code_promoted",
                {
                    "status": "PROMOTED" if not config.SANDBOX_READ_ONLY else "DRY_RUN",
                    "files": list(generated_files.keys()),
                    "context": task_context.to_dict(),
                },
                task_description=task_context.task,
            )

        # 9. Finalize Task
        self._finalize_task(task_description, plan, generated_files, is_approved)
