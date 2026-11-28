import os
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
        self,
        repo_files: List[str],
        plan: str,
        spec: str,
        summarize_references: bool = False,
    ) -> Dict[str, str]:
        return self.coding_stage.collect_repo_files_content(
            repo_files, plan, spec, summarize_references=summarize_references
        )

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

    def _update_store(self, task_id: Optional[str], **updates: Any) -> None:
        task_store = getattr(self.orch, "task_store", None)
        if task_id and task_store is not None:
            task_store.update_task(task_id, **updates)

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

        task_store = getattr(self.orch, "task_store", None)
        task_record = (
            task_store.create_task(
                task_description=task_description,
                task_name=safe_task_name,
                complexity=complexity,
                model_override=model_override,
            )
            if task_store is not None
            else None
        )

        self._run_stages(
            task_description=task_description,
            complexity=complexity,
            task_context=task_context,
            model_override=model_override,
            task_record=task_record,
            is_resume=False,
        )

    def resume(self, task_record: Dict[str, Any], model_override: Optional[str] = None) -> None:
        """Resume a previously recorded task without re-classifying a 'continue' prompt."""
        task_description = str(task_record["task_description"])
        safe_task_name = str(
            task_record.get("task_name") or self.orch.workspace.generate_task_slug(task_description)
        )
        effective_model_override = (
            model_override if model_override is not None else task_record.get("model_override")
        )

        self.orch.display.show_task_header(
            f"[RESUMING] {task_description}",
            self.orch.repo_path,
            self.orch.allowed_directory,
        )

        task_context = TaskContext(
            task=task_description,
            task_name=safe_task_name,
            repo_path=self.orch.repo_path,
            allowed_directory=self.orch.allowed_directory,
        )
        if task_record.get("bootstrap_config"):
            task_context.bootstrap_config = dict(task_record["bootstrap_config"])

        complexity = task_record.get("complexity")
        if not complexity:
            complexity = self.planning_stage.classify_task(task_description, task_context)
        else:
            task_context.complexity = str(complexity)
            self.orch.display.show_complexity(str(complexity))

        task_id = task_record.get("task_id")
        self._update_store(
            task_id,
            status="in_progress",
            task_name=safe_task_name,
            complexity=str(complexity),
            model_override=effective_model_override,
        )

        self._run_stages(
            task_description=task_description,
            complexity=str(complexity),
            task_context=task_context,
            model_override=effective_model_override,
            task_record=task_record,
            is_resume=True,
        )

    def _run_stages(
        self,
        task_description: str,
        complexity: str,
        task_context: TaskContext,
        model_override: Optional[str] = None,
        task_record: Optional[Dict[str, Any]] = None,
        is_resume: bool = False,
    ) -> None:
        task_id = task_record.get("task_id") if task_record else None
        plan_rel_path = (
            str(task_record["plan_file"])
            if task_record and task_record.get("plan_file")
            else os.path.join(".maca", task_context.task_name, "plan.md")
        )
        spec_rel_path = (
            str(task_record["spec_file"])
            if task_record and task_record.get("spec_file")
            else os.path.join(".maca", task_context.task_name, "spec.md")
        )
        abs_plan_path = os.path.join(self.orch.repo_path, plan_rel_path)
        abs_spec_path = os.path.join(self.orch.repo_path, spec_rel_path)

        try:
            # 2. Select Model Client
            model_name, client = ModelRouter.select_model(
                complexity=complexity,
                model_override=model_override,
                is_gemini_online_fn=self.orch._is_gemini_online,
                is_claude_online_fn=self.orch._is_claude_online,
            )
            self.orch.display.show_model_selection(model_name, model_override)

            # 2.5 Clarify & 3. Planning Step (reuse saved plan on resume if present)
            if is_resume and os.path.exists(abs_plan_path):
                self.orch.display.show_step_header(
                    "Step 1: Resuming with saved implementation plan...",
                    plan_rel_path,
                )
                plan = self.orch.workspace.read_file(plan_rel_path)
                task_context.plan = plan
                repo_files = (
                    [] if task_context.bootstrap_config else self.orch.workspace.list_files()
                )
            else:
                if not (is_resume and task_context.bootstrap_config):
                    bootstrap_config = self.planning_stage.clarify_task(
                        task_description, task_context, client=client, model_name=model_name
                    )
                    if bootstrap_config:
                        self._update_store(
                            task_id, stage="clarified", bootstrap_config=bootstrap_config
                        )

                plan, repo_files = self.planning_stage.plan_task(
                    task_description, task_context, client, model_name
                )
                self._update_store(task_id, stage="planned", plan_file=plan_rel_path)

            # 4. Specification Step (reuse saved spec on resume if present)
            if complexity == "SIMPLE":
                spec: Optional[str] = self.planning_stage.spec_task(
                    task_description, plan, complexity, client, model_name, task_context
                )
            elif is_resume and os.path.exists(abs_spec_path):
                self.orch.display.show_step_header(
                    "Step 1.5: Resuming with saved technical specification...",
                    spec_rel_path,
                )
                spec = self.orch.workspace.read_file(spec_rel_path)
                task_context.spec = spec
            else:
                spec = self.planning_stage.spec_task(
                    task_description, plan, complexity, client, model_name, task_context
                )
                if spec is None:
                    self._update_store(
                        task_id,
                        status="paused",
                        stage="spec_ready",
                        spec_file=spec_rel_path,
                    )
                    return  # Cancelled by user
                self._update_store(task_id, stage="spec_ready", spec_file=spec_rel_path)

            if spec is None:
                return

            # 5. Coding & Completion Verification Loop
            repo_files_content = self.coding_stage.collect_repo_files_content(
                repo_files, plan, spec
            )
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
            self._update_store(task_id, stage="coded", generated_files=list(generated_files.keys()))

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
            self._update_store(
                task_id, stage="reviewed", generated_files=list(generated_files.keys())
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
            self._update_store(
                task_id,
                status="completed" if is_approved else "revision_failed",
                stage="completed",
                generated_files=list(generated_files.keys()),
            )
        except KeyboardInterrupt:
            self._update_store(task_id, status="interrupted")
            raise
        except Exception:
            self._update_store(task_id, status="failed")
            raise
