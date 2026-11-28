import os
from typing import Any, Dict, List, Optional, Tuple, cast

from maca.agents.clarifier import ClarifierAgent
from maca.agents.planner import PlannerAgent
from maca.agents.spec import SpecAgent
from maca.context import TaskContext
from maca.repo_summarizer import build_repo_map
from maca.rich_compat import Console, Prompt
from maca.stages.common import (
    _get_orch_attr,
    _is_mock,
    build_agent_payload,
    record_step_progress,
)

console = Console()


class PlanningStage:
    """Manages task classification, implementation planning, and technical specification

    generation including interactive human approval checkpoints.
    """

    def __init__(self, orchestrator: Any):
        self.orch = orchestrator

    def classify_task(self, task_description: str, task_context: TaskContext) -> str:
        with console.status("[bold yellow]Evaluating task complexity...", spinner="dots"):
            evaluator = self.orch.evaluator
            if _is_mock(getattr(evaluator, "evaluate", None)) or _is_mock(evaluator):
                complexity = evaluator.evaluate(task_description)
            else:
                try:
                    payload = {
                        "task_description": task_description,
                        "context": task_context.to_dict(),
                    }
                    classifier_result = self.orch.call_agent("maca.agents.task_classifier", payload)
                    complexity = classifier_result.get("result", "SIMPLE")
                except Exception:
                    complexity = evaluator.evaluate(task_description)

        task_context.complexity = complexity
        task_context.update_agent(
            "task_classifier",
            completed=True,
            summary=f"Complexity evaluated as {complexity}",
            details={"complexity": complexity},
        )
        self.orch.display.show_complexity(complexity)
        return str(complexity)

    def clarify_task(
        self,
        task_description: str,
        task_context: TaskContext,
        client: Any = None,
        model_name: Optional[str] = None,
        interactive: bool = True,
    ) -> Optional[Dict[str, str]]:
        prompt_cls = _get_orch_attr("Prompt", Prompt)
        prompt_ask_fn = getattr(prompt_cls, "ask", None) if interactive else None

        clarifier_client = (
            client
            or getattr(self.orch.evaluator, "gemma_client", None)
            or getattr(getattr(self.orch, "evaluator", None), "gemma_client", None)
        )
        if not clarifier_client or not hasattr(clarifier_client, "generate"):
            from maca.models.local_gemma import LocalGemmaClient

            clarifier_client = LocalGemmaClient()

        clarifier_cls = _get_orch_attr("ClarifierAgent", ClarifierAgent)
        clarifier_agent = clarifier_cls(clarifier_client, repo_path=self.orch.repo_path)

        bootstrap_config = clarifier_agent.clarify(
            task_description=task_description,
            prompt_ask_fn=prompt_ask_fn,
            interactive=interactive,
            task_name=task_context.task_name,
        )

        if bootstrap_config:
            framework = bootstrap_config.get("framework", "Framework")
            self.orch.display.show_step_header(
                "Step 0.5: Framework Bootstrap Clarification",
                f"Configuring architectural choices for {framework}",
            )
            task_context.bootstrap_config = bootstrap_config
            record_step_progress(
                self.orch,
                task_context,
                "clarifier",
                "clarification",
                "COMPLETED",
                f"Resolved {framework} bootstrap configuration",
                details=bootstrap_config,
            )
            if hasattr(self.orch.display, "show_bootstrap_config"):
                self.orch.display.show_bootstrap_config(bootstrap_config)

        return cast(Optional[Dict[str, str]], bootstrap_config)

    def _get_effective_task_description(
        self, task_description: str, task_context: TaskContext
    ) -> str:
        if not task_context.bootstrap_config:
            return task_description
        config_lines = "\n".join(
            f"- {k.replace('_', ' ').title()}: {v}"
            for k, v in task_context.bootstrap_config.items()
        )
        return (
            f"{task_description}\n\n[Framework Bootstrap Configuration]:\n{config_lines}\n"
            f"- Project Root Layout: Place all project files (e.g. pom.xml, build.gradle, src/...) "
            f"directly at the root of the workspace (do NOT nest inside existing unrelated subdirectories)."
        )

    def plan_task(
        self,
        task_description: str,
        task_context: TaskContext,
        client: Any,
        model_name: str,
    ) -> Tuple[str, List[str]]:
        effective_task = self._get_effective_task_description(task_description, task_context)
        planner_cls = _get_orch_attr("PlannerAgent", PlannerAgent)
        planner = planner_cls(
            client, repo_path=self.orch.repo_path, allowed_directory=self.orch.allowed_directory
        )
        if _is_mock(planner.list_files):
            repo_files = planner.list_files(self.orch.repo_path)
        elif task_context.bootstrap_config:
            repo_files = []
        else:
            repo_files = self.orch.workspace.list_files()

        repo_map = ""
        if (
            repo_files
            and not _is_mock(planner_cls)
            and not _is_mock(planner.run)
            and not _is_mock(self.orch.workspace)
            and not _is_mock(self.orch.workspace.read_file)
        ):
            repo_map = build_repo_map(repo_files, self.orch.workspace.read_file)

        self.orch.display.show_step_header("Step 1: Planner Agent starting...")
        with console.status(
            "[bold yellow]Planner Agent is generating the implementation plan...[/bold yellow]",
            spinner="dots",
        ):
            if _is_mock(planner_cls) or _is_mock(planner.run):
                plan = planner.run(
                    effective_task,
                    repo_files,
                    history=self.orch.conversation_history,
                    task_name=task_context.task_name,
                )
            else:
                payload = build_agent_payload(
                    self.orch,
                    task_context,
                    model_name,
                    task_description=effective_task,
                    repo_files=repo_files,
                    repo_map=repo_map,
                )
                plan = self.orch.call_agent("maca.agents.planner", payload).get("result", "")

        plan_rel_path = os.path.join(".maca", task_context.task_name, "plan.md")
        self.orch.workspace.write_file(plan_rel_path, plan)
        self.orch.display.show_plan(plan, os.path.join(self.orch.repo_path, plan_rel_path))

        task_context.plan = plan
        record_step_progress(
            self.orch,
            task_context,
            "planner",
            "planning",
            "COMPLETED",
            "Generated structured implementation plan",
            details={"plan_file": plan_rel_path},
            file_path=plan_rel_path,
        )
        return plan, repo_files

    def spec_task(
        self,
        task_description: str,
        plan: str,
        complexity: str,
        client: Any,
        model_name: str,
        task_context: TaskContext,
    ) -> Optional[str]:
        effective_task = self._get_effective_task_description(task_description, task_context)
        plan_rel_path = os.path.join(".maca", task_context.task_name, "plan.md")
        if complexity == "SIMPLE":
            self.orch.display.show_step_header("Step 1.5: Spec Agent skipped for SIMPLE task...")
            task_context.spec = plan
            record_step_progress(
                self.orch,
                task_context,
                "spec",
                "specification",
                "SKIPPED_FOR_SIMPLE",
                "Skipped for SIMPLE task",
                file_path=plan_rel_path,
            )
            return plan

        spec_cls = _get_orch_attr("SpecAgent", SpecAgent)
        self.orch.display.show_step_header("Step 1.5: Spec Agent starting...")
        with console.status(
            "[bold yellow]Spec Agent is generating the technical specification...[/bold yellow]",
            spinner="dots",
        ):
            if _is_mock(spec_cls):
                spec_agent = spec_cls(
                    client,
                    repo_path=self.orch.repo_path,
                    allowed_directory=self.orch.allowed_directory,
                )
                spec = spec_agent.run(
                    effective_task,
                    plan,
                    history=self.orch.conversation_history,
                    task_name=task_context.task_name,
                )
            else:
                payload = build_agent_payload(
                    self.orch, task_context, model_name, task_description=effective_task, plan=plan
                )
                spec = self.orch.call_agent("maca.agents.spec", payload).get("result", "")

        spec_rel_path = os.path.join(".maca", task_context.task_name, "spec.md")
        self.orch.workspace.write_file(spec_rel_path, spec)
        self.orch.display.show_spec(spec, os.path.join(self.orch.repo_path, spec_rel_path))

        task_context.spec = spec
        record_step_progress(
            self.orch,
            task_context,
            "spec",
            "specification",
            "COMPLETED",
            "Generated technical specification",
            details={"spec_file": spec_rel_path},
            file_path=spec_rel_path,
        )

        prompt_cls = _get_orch_attr("Prompt", Prompt)
        user_input = prompt_cls.ask(
            f"\n[bold yellow]Spec is ready for review at {spec_rel_path}[/bold yellow]\n[cyan]Modify it if needed. Press Enter to approve and continue, or type '/cancel' to abort[/cyan]"
        )
        if user_input.strip().lower() == "/cancel":
            console.print("[bold red]Task cancelled by user.[/bold red]")
            record_step_progress(
                self.orch,
                task_context,
                "spec",
                "specification",
                "CANCELLED_BY_USER",
                "Cancelled by user",
            )
            return None

        if _is_mock(spec_cls):
            spec = spec_cls(client, repo_path=self.orch.repo_path).read_file(
                os.path.join(self.orch.repo_path, spec_rel_path)
            )
        else:
            spec = self.orch.workspace.read_file(spec_rel_path)

        record_step_progress(
            self.orch,
            task_context,
            "spec",
            "specification",
            "APPROVED",
            "Approved by user",
            file_path=spec_rel_path,
        )
        return str(spec) if spec is not None else None
