from typing import Any, Dict, List, Optional, Tuple, cast

from maca import maca_config as config
from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent
from maca.context import TaskContext
from maca.delta_context import build_delta_file_context
from maca.rich_compat import Console
from maca.stages.common import (
    _get_orch_attr,
    _is_mock,
    build_agent_payload,
)
from maca.stages.nudge import NudgeLoopRunner

console = Console()


class CodingStage:
    """Manages file context gathering, coder execution (SimpleCoder vs SpecCoder),

    and the completion verification loop.
    """

    def __init__(self, orchestrator: Any):
        self.orch = orchestrator

    def collect_repo_files_content(
        self, repo_files: List[str], plan: str, spec: str
    ) -> Dict[str, str]:
        repo_files_content = {}
        plan_lower = plan.lower().replace("\\", "/")
        spec_lower = spec.lower().replace("\\", "/")
        for filepath in repo_files:
            norm_path = filepath.replace("\\", "/").lower()
            if norm_path in spec_lower or norm_path in plan_lower:
                content = self.orch.workspace.read_file(filepath)
                if not content.startswith("Error"):
                    repo_files_content[filepath] = content
        return repo_files_content

    def run_coder_step(
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
        simple_coder_cls = _get_orch_attr("SimpleCoderAgent", SimpleCoderAgent)
        spec_coder_cls = _get_orch_attr("SpecCoderAgent", SpecCoderAgent)

        coder = (
            simple_coder_cls(
                "SimpleCoder",
                client,
                repo_path=self.orch.repo_path,
                allowed_directory=self.orch.allowed_directory,
            )
            if coder_type == "SIMPLE"
            else spec_coder_cls(
                "SpecCoder",
                client,
                repo_path=self.orch.repo_path,
                allowed_directory=self.orch.allowed_directory,
            )
        )

        effective_task = task_description if not nudge else f"{task_description}\n\nNudge: {nudge}"

        if _is_mock(spec_coder_cls) or _is_mock(simple_coder_cls) or _is_mock(coder.run):
            if coder_type == "SIMPLE":
                coder_response = coder.run(
                    task_description=effective_task,
                    plan=plan,
                    repo_files_content=repo_files_content,
                    history=self.orch.conversation_history,
                    task_name=task_context.task_name,
                    nudge=nudge,
                )
            else:
                coder_response = coder.run(
                    task_description=effective_task,
                    spec=spec,
                    repo_files_content=repo_files_content,
                    history=self.orch.conversation_history,
                    task_name=task_context.task_name,
                    nudge=nudge,
                )
            files = coder.parse_files(coder_response)
            file_blocks = self.orch.workspace.compute_file_blocks(files, repo_files_content)
        else:
            payload = build_agent_payload(
                self.orch,
                task_context,
                model_name,
                coder_type=coder_type,
                task_description=effective_task,
                plan=plan,
                spec=spec,
                repo_files_content=repo_files_content,
                nudge=nudge,
            )
            coder_result = self.orch.call_agent("maca.agents.coder", payload)
            coder_response = coder_result.get("result", "")
            files = coder_result.get("files", {})
            file_blocks = coder_result.get(
                "file_blocks"
            ) or self.orch.workspace.compute_file_blocks(files, repo_files_content)

        return files, file_blocks, coder_response

    def apply_coder_update(
        self,
        updated_files: Dict[str, str],
        generated_files: Dict[str, str],
        repo_files_content: Dict[str, str],
        task_context: TaskContext,
        summary_label: str,
        persist_changes: bool = False,
    ) -> Dict[str, Any]:
        for fp, content in updated_files.items():
            generated_files[fp] = content
        file_blocks = self.orch.workspace.compute_file_blocks(generated_files, repo_files_content)
        if updated_files:
            self.orch.workspace.flush_to_staging(task_context.task_name, updated_files)
        if persist_changes and not config.SANDBOX_READ_ONLY:
            self.orch.workspace.apply_changes(updated_files, sandbox_read_only=False)
        task_context.refresh_todo_status()
        task_context.update_agent(
            "coder",
            completed=True,
            summary=f"Updated {len(updated_files)} files after {summary_label}",
            details={"files": list(generated_files.keys()), "file_blocks": file_blocks},
        )
        return cast(Dict[str, Any], file_blocks)

    def completion_verification_loop(
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
        max_nudge_attempts = 10
        for attempt in range(max_nudge_attempts):
            console.print(
                f"[bold yellow]Checking if Coder completed all planned steps (Attempt {attempt + 1})...[/bold yellow]"
            )
            is_done, feedback = self.orch._is_coder_done(
                client,
                task_description,
                spec,
                generated_files,
                task_name=task_context.task_name,
                context=task_context.to_dict(),
            )
            task_context.refresh_todo_status()
            task_context.update_agent(
                "code_completion_verifier",
                completed=is_done,
                summary="All planned tasks confirmed complete"
                if is_done
                else f"Missing tasks: {feedback[:80]}",
                details={"is_done": is_done, "feedback": feedback},
            )
            if is_done:
                console.print(
                    "[bold green]Coder confirmed all planned tasks are complete![/bold green]"
                )
                break

            console.print(
                f"[bold red]Coder has NOT completed all steps. Feedback:[/bold red]\n{feedback}"
            )
            if attempt == max_nudge_attempts - 1:
                console.print(
                    "[bold red]Reached maximum coder nudge attempts. Proceeding to review.[/bold red]"
                )
                break

            nudge_prompt = (
                f"You have not completed all the steps in the plan. Here is the feedback on what is missing:\n\n"
                f"{feedback}\n\n"
                f"Please continue implementing the missing parts and output the complete updated files."
            )
            delta_files = build_delta_file_context(repo_files_content, generated_files, feedback)
            updated_blocks = NudgeLoopRunner.run_nudge_iteration(
                run_coder_fn=self.run_coder_step,
                apply_update_fn=lambda updated_files, summary_label, persist_changes: (
                    self.apply_coder_update(
                        updated_files=updated_files,
                        generated_files=generated_files,
                        repo_files_content=repo_files_content,
                        task_context=task_context,
                        summary_label=summary_label,
                        persist_changes=persist_changes,
                    )
                ),
                nudge_prompt=nudge_prompt,
                nudge_label="finish the task",
                spinner_message="Coder Agent is continuing implementation based on todo list...",
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

        return generated_files, file_blocks

    def code_and_verify(
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
        effective_task = task_description
        if task_context.bootstrap_config:
            config_lines = "\n".join(
                f"- {k.replace('_', ' ').title()}: {v}"
                for k, v in task_context.bootstrap_config.items()
            )
            effective_task = (
                f"{task_description}\n\n[Framework Bootstrap Configuration]:\n{config_lines}"
            )

        coder_type = "SIMPLE" if complexity == "SIMPLE" else "SPEC"
        self.orch.display.show_step_header("Step 2: Coder Agent starting...")
        with console.status(
            f"[bold yellow]{coder_type} Coder Agent is implementing the task...[/bold yellow]",
            spinner="dots",
        ):
            generated_files, file_blocks, coder_response = self.run_coder_step(
                coder_type=coder_type,
                task_description=effective_task,
                plan=plan,
                spec=spec,
                repo_files_content=repo_files_content,
                client=client,
                model_name=model_name,
                task_context=task_context,
            )

        task_context.refresh_todo_status()
        task_context.update_agent(
            "coder",
            completed=bool(generated_files),
            summary=f"Generated {len(generated_files)} files",
            details={"files": list(generated_files.keys()), "file_blocks": file_blocks},
        )
        self.orch.display.show_generated_files(generated_files, coder_response)

        if generated_files:
            self.orch.workspace.flush_to_staging(task_context.task_name, generated_files)

        return self.completion_verification_loop(
            client=client,
            task_description=effective_task,
            plan=plan,
            spec=spec,
            generated_files=generated_files,
            file_blocks=file_blocks,
            repo_files_content=repo_files_content,
            coder_type=coder_type,
            model_name=model_name,
            task_context=task_context,
        )
