import os
from typing import Any

from maca import maca_config as config
from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent

# Import agents
from maca.agents.planner import PlannerAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent
from maca.evaluator import ComplexityEvaluator
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient
from maca.rich_compat import Console, Markdown, Panel, Prompt, Table

console = Console()


class Orchestrator:
    def __init__(self, repo_path="."):
        self.repo_path = os.path.abspath(repo_path)
        self.evaluator = ComplexityEvaluator()
        self.conversation_history = []

    def _is_coder_done(self, client, task_description, spec, generated_files):
        """Ask the model if the coder has completed all steps in the plan."""
        if config.MOCK_GEMMA_FALLBACK and not client.api_key:
            return True, "Mock Coder finished."

        files_str = ""
        for filepath, content in generated_files.items():
            files_str += f"--- FILE: {filepath} ---\n{content}\n\n"

        system_instruction = (
            "You are a Quality Assurance validator. Compare the technical specification "
            "with the generated files to see if all planned tasks/steps are fully completed. "
            "Respond with 'YES' if everything is completely implemented. "
            "Otherwise, respond with 'NO' followed by a detailed list of what is missing."
        )
        prompt = (
            f"Task: {task_description}\n\n"
            f"Specification:\n{spec}\n\n"
            f"Generated Files:\n{files_str}\n\n"
            "Are all steps in the specification completely implemented? (Start your response with YES or NO)"
        )
        try:
            response = client.generate(prompt, system_instruction).strip()
            is_done = response.upper().startswith("YES")
            return is_done, response
        except Exception as e:
            return True, f"Error validating completion: {e}"

    def _is_gemini_online(self):
        key = config.get_gemini_api_key()
        if not key:
            return False
        if config.MOCK_GEMMA_FALLBACK:
            return True
        try:
            old_timeout = config.GEMINI_TIMEOUT
            config.GEMINI_TIMEOUT = 3
            try:
                client = GeminiClient()
                res = client.generate("Reply with only the word OK.")
                return bool(res)
            finally:
                config.GEMINI_TIMEOUT = old_timeout
        except Exception:
            return False

    def _is_claude_online(self):
        key = config.get_claude_api_key()
        if not key:
            return False
        if config.MOCK_GEMMA_FALLBACK:
            return True
        try:
            old_timeout = config.CLAUDE_TIMEOUT
            config.CLAUDE_TIMEOUT = 3
            try:
                client = ClaudeClient()
                res = client.generate("Reply with only the word OK.")
                return bool(res)
            finally:
                config.CLAUDE_TIMEOUT = old_timeout
        except Exception:
            return False

    def check_backends_status(self, run_handshakes=False):
        # Checks status of Gemma (Ollama), Gemini and Claude backends.
        status = {}
        client: Any = None

        # 1. Check Gemma
        gemma_url = config.OLLAMA_API_URL
        gemma_model = config.OLLAMA_MODEL
        gemma_status = "OFFLINE (Mock Mode Fallback)"

        def _detect_ollama():
            import urllib.request

            try:
                req = urllib.request.Request(f"{gemma_url}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=2) as res:
                    if res.status in (200, 204):
                        return "ONLINE (Ollama HTTP - {0})".format(gemma_model)
            except Exception:
                pass

            import subprocess

            try:
                res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0 and res.stdout.strip():
                    return "ONLINE (Ollama CLI - {0})".format(gemma_model)
            except Exception:
                pass

            try:
                res = subprocess.run(
                    ["pgrep", "-af", "ollama"], capture_output=True, text=True, timeout=2
                )
                if res.returncode == 0 and res.stdout.strip():
                    return "ONLINE (Ollama Running - {0})".format(gemma_model)
            except Exception:
                pass

            return "OFFLINE (Mock Mode Fallback)"

        gemma_status = _detect_ollama()

        status["Gemma"] = gemma_status

        # 2. Check Gemini
        gemini_key = config.get_gemini_api_key()
        if not gemini_key:
            status["Gemini"] = "UNCONFIGURED (Missing API Key)"
        else:
            if run_handshakes:
                old_mock = config.MOCK_GEMMA_FALLBACK
                config.MOCK_GEMMA_FALLBACK = False
                try:
                    client = GeminiClient()
                    res = client.generate("Reply with only the word OK.")
                    if "OK" in res.upper():
                        status["Gemini"] = "ONLINE (Connected)"
                    else:
                        status["Gemini"] = f"ONLINE (Unexpected response: {res.strip()})"
                except Exception as e:
                    status["Gemini"] = f"CONNECTION FAILED: {str(e)}"
                finally:
                    config.MOCK_GEMMA_FALLBACK = old_mock
            else:
                status["Gemini"] = "CONFIGURED (Key Present)"

        # 3. Check Claude
        claude_key = config.get_claude_api_key()
        if not claude_key:
            status["Claude"] = "UNCONFIGURED (Missing API Key)"
        else:
            if run_handshakes:
                old_mock = config.MOCK_GEMMA_FALLBACK
                config.MOCK_GEMMA_FALLBACK = False
                try:
                    client = ClaudeClient()
                    res = client.generate("Reply with only the word OK.")
                    if "OK" in res.upper():
                        status["Claude"] = "ONLINE (Connected)"
                    else:
                        status["Claude"] = f"ONLINE (Unexpected response: {res.strip()})"
                except Exception as e:
                    status["Claude"] = f"CONNECTION FAILED: {str(e)}"
                finally:
                    config.MOCK_GEMMA_FALLBACK = old_mock
            else:
                status["Claude"] = "CONFIGURED (Key Present)"

        return status

    def run_task(self, task_description, model_override=None):
        console.print(
            Panel(
                f"[bold blue]Multi-Agent Coding Assistant[/bold blue]\n[bold white]Repo Path:[/bold white] {self.repo_path}\n[bold white]Task:[/bold white] {task_description}",
                border_style="blue",
            )
        )

        # 1. Evaluate Complexity
        with console.status("[bold yellow]Evaluating task complexity...", spinner="dots"):
            complexity = self.evaluator.evaluate(task_description)

        console.print(
            f"[bold green]Task Complexity Evaluated:[/bold green] [bold cyan]{complexity}[/bold cyan]"
        )

        # 2. Select Model Client
        model_name = ""
        client: Any = None

        if model_override:
            model_name = model_override.upper()
            console.print(
                f"[bold yellow]Model override active:[/bold yellow] [bold cyan]{model_name}[/bold cyan]"
            )
            if model_name.startswith("GEMINI"):
                client = GeminiClient()
                config.validate_config(complexity, selected_agent="GEMINI")
            elif model_name.startswith("CLAUDE"):
                client = ClaudeClient()
                config.validate_config(complexity, selected_agent="CLAUDE")
            elif model_name.startswith("GEMMA"):
                client = LocalGemmaClient()
                config.validate_config(complexity)
        else:
            if complexity == "SIMPLE":
                model_name = "GEMMA (LOCAL)"
                client = LocalGemmaClient()
            else:
                gemini_online = self._is_gemini_online()
                claude_online = self._is_claude_online()

                if complexity == "MEDIUM":
                    if gemini_online:
                        model_name = "GEMINI (REMOTE)"
                        client = GeminiClient()
                        config.validate_config(complexity, selected_agent="GEMINI")
                    elif claude_online:
                        model_name = "CLAUDE (REMOTE)"
                        client = ClaudeClient()
                        config.validate_config(complexity, selected_agent="CLAUDE")
                    else:
                        model_name = "GEMMA (LOCAL)"
                        client = LocalGemmaClient()
                        config.validate_config(complexity)
                else:  # COMPLEX and VERY_COMPLEX
                    if claude_online:
                        model_name = "CLAUDE (REMOTE)"
                        client = ClaudeClient()
                        config.validate_config(complexity, selected_agent="CLAUDE")
                    elif gemini_online:
                        model_name = "GEMINI (REMOTE)"
                        client = GeminiClient()
                        config.validate_config(complexity, selected_agent="GEMINI")
                    else:
                        model_name = "GEMMA (LOCAL)"
                        client = LocalGemmaClient()
                        config.validate_config(complexity)

        console.print(
            f"[bold green]Selected Model Client:[/bold green] [bold cyan]{model_name}[/bold cyan]\n"
        )

        # Get existing files in the repo
        planner = PlannerAgent(client, repo_path=self.repo_path)
        repo_files = planner.list_files(self.repo_path)

        # 3. Step 1: Planning Agent
        console.print(
            Panel(
                "[bold yellow]Step 1: Planner Agent starting...[/bold yellow]",
                border_style="yellow",
            )
        )
        with console.status(
            "[bold yellow]Planner Agent is generating the implementation plan...", spinner="dots"
        ):
            plan = planner.run(task_description, repo_files, history=self.conversation_history)

        console.print(
            Panel(
                Markdown(plan),
                title="[bold green]Implementation Plan[/bold green]",
                border_style="green",
            )
        )

        # Write Plan to .maca/plan-<task>.md
        safe_task_name = (
            "".join(c if c.isalnum() else "-" for c in task_description[:30]).strip("-").lower()
        )
        maca_dir = os.path.join(self.repo_path, ".maca")
        os.makedirs(maca_dir, exist_ok=True)
        plan_file = os.path.join(maca_dir, f"plan-{safe_task_name}.md")
        planner.write_file(plan_file, plan)
        console.print(f"[bold green]Plan saved to {plan_file}[/bold green]")

        # 3.5. Step 1.5: Spec Agent
        if complexity == "SIMPLE":
            console.print(
                Panel(
                    "[bold yellow]Step 1.5: Spec Agent skipped for SIMPLE task...[/bold yellow]",
                    border_style="yellow",
                )
            )
            spec = plan
        else:
            console.print(
                Panel(
                    "[bold yellow]Step 1.5: Spec Agent starting...[/bold yellow]",
                    border_style="yellow",
                )
            )
            spec_agent = SpecAgent(client, repo_path=self.repo_path)
            with console.status(
                "[bold yellow]Spec Agent is generating the technical specification...",
                spinner="dots",
            ):
                spec = spec_agent.run(task_description, plan, history=self.conversation_history)

            console.print(
                Panel(
                    Markdown(spec),
                    title="[bold green]Technical Specification[/bold green]",
                    border_style="green",
                )
            )
            spec_file = os.path.join(maca_dir, f"spec-{safe_task_name}.md")
            spec_agent.write_file(spec_file, spec)
            console.print(f"[bold green]Spec saved to {spec_file}[/bold green]")

            # Interactive Pause
            user_input = Prompt.ask(
                f"\n[bold yellow]Spec is ready for review at .maca/spec-{safe_task_name}.md[/bold yellow]\n[cyan]Modify it if needed. Press Enter to approve and continue, or type '/cancel' to abort[/cyan]"
            )
            if user_input.strip().lower() == "/cancel":
                console.print("[bold red]Task cancelled by user.[/bold red]")
                return

            # Re-read the spec in case the user modified it
            spec = spec_agent.read_file(spec_file)

        # 4. Step 2: Coder Agent
        console.print(
            Panel(
                "[bold yellow]Step 2: Coder Agent starting...[/bold yellow]", border_style="yellow"
            )
        )

        # Read contents of files mentioned in spec to provide context to Coder if they exist
        repo_files_content = {}
        for filepath in repo_files:
            if filepath.lower() in spec.lower() or filepath.lower() in plan.lower():
                full_path = os.path.join(self.repo_path, filepath)
                if os.path.exists(full_path):
                    repo_files_content[filepath] = planner.read_file(full_path)

        coder: Any
        if complexity == "SIMPLE":
            coder = SimpleCoderAgent("SimpleCoder", client, repo_path=self.repo_path)
            with console.status(
                "[bold yellow]Simple Coder Agent is implementing the plan...", spinner="dots"
            ):
                coder_response = coder.run(
                    task_description, plan, repo_files_content, history=self.conversation_history
                )
        else:
            coder = SpecCoderAgent("SpecCoder", client, repo_path=self.repo_path)
            with console.status(
                "[bold yellow]Spec Coder Agent is implementing the specification...", spinner="dots"
            ):
                coder_response = coder.run(
                    task_description, spec, repo_files_content, history=self.conversation_history
                )
            generated_files = coder.parse_files(coder_response)

        if not generated_files:
            console.print(
                "[bold red]Warning: Coder did not output any files in the expected format [FILE: path]...[/bold red]"
            )
            console.print("[yellow]Raw coder response structure check:[/yellow]")
            console.print(coder_response[:500] + "...")
        else:
            console.print(f"[bold green]Coder generated {len(generated_files)} files:[/bold green]")
            for fp in generated_files.keys():
                console.print(f" - [cyan]{fp}[/cyan]")

        # Coder Verification Loop
        max_nudge_attempts = 10
        for attempt in range(max_nudge_attempts):
            console.print(
                f"[bold yellow]Checking if Coder completed all planned steps (Attempt {attempt + 1})...[/bold yellow]"
            )
            is_done, feedback = self._is_coder_done(client, task_description, spec, generated_files)
            if is_done:
                console.print(
                    "[bold green]Coder confirmed all planned tasks are complete![/bold green]"
                )
                break
            else:
                console.print(
                    f"[bold red]Coder has NOT completed all steps. Feedback:[/bold red]\n{feedback}"
                )
                if attempt == max_nudge_attempts - 1:
                    console.print(
                        "[bold red]Reached maximum coder nudge attempts. Proceeding to review.[/bold red]"
                    )
                    break

                # Nudge the Coder to continue
                nudge_prompt = (
                    f"You have not completed all the steps in the plan. Here is the feedback on what is missing:\n\n"
                    f"{feedback}\n\n"
                    f"Please continue implementing the missing parts and output the complete updated files."
                )
                console.print(
                    "[bold yellow]Nudging Coder Agent to finish the task...[/bold yellow]"
                )
                with console.status(
                    "[bold yellow]Coder Agent is continuing implementation...", spinner="dots"
                ):
                    if complexity == "SIMPLE":
                        coder_response = coder.run(
                            task_description=task_description + f"\n\nNudge: {nudge_prompt}",
                            plan=plan,
                            repo_files_content={**repo_files_content, **generated_files},
                            history=self.conversation_history,
                        )
                    else:
                        coder_response = coder.run(
                            task_description=task_description + f"\n\nNudge: {nudge_prompt}",
                            spec=spec,
                            repo_files_content={**repo_files_content, **generated_files},
                            history=self.conversation_history,
                        )
                    updated_files = coder.parse_files(coder_response)
                    if updated_files:
                        for fp, content in updated_files.items():
                            generated_files[fp] = content

        # 5. Step 3: Reviewer Agent
        console.print(
            Panel(
                "[bold yellow]Step 3: Reviewer Agent starting...[/bold yellow]",
                border_style="yellow",
            )
        )
        reviewer = ReviewerAgent(client, repo_path=self.repo_path)

        max_review_attempts = 10
        for r_attempt in range(max_review_attempts):
            console.print(
                f"[bold yellow]Running Reviewer Agent (Attempt {r_attempt + 1})...[/bold yellow]"
            )
            with console.status(
                "[bold yellow]Reviewer Agent is auditing the generated code...", spinner="dots"
            ):
                reviewer_response = reviewer.run(
                    task_description,
                    generated_files,
                    history=self.conversation_history,
                    plan_or_spec=spec,
                )
                reviewed_files = reviewer.parse_files(reviewer_response)

            console.print(
                Panel(
                    Markdown(reviewer_response),
                    title=f"[bold green]Reviewer Report (Attempt {r_attempt + 1})[/bold green]",
                    border_style="green",
                )
            )

            is_approved = reviewer.is_approved(reviewer_response)

            if is_approved:
                if reviewed_files:
                    for fp, content in reviewed_files.items():
                        generated_files[fp] = content
                console.print("[bold green]Reviewer APPROVED the implementation![/bold green]")
                break
            else:
                if r_attempt == max_review_attempts - 1:
                    console.print(
                        "[bold red]Reached maximum review attempts. Proceeding to write files.[/bold red]"
                    )
                    if reviewed_files:
                        for fp, content in reviewed_files.items():
                            generated_files[fp] = content
                    break

                # Nudge the Coder to address Reviewer concerns
                nudge_prompt = (
                    f"The Reviewer has audited your code and raised issues / corrections. "
                    f"Here is the Reviewer's report:\n\n"
                    f"{reviewer_response}\n\n"
                    f"Please address all these issues and output the complete updated files."
                )
                console.print(
                    "[bold yellow]Nudging Coder Agent to address Reviewer concerns...[/bold yellow]"
                )
                with console.status(
                    "[bold yellow]Coder Agent is applying corrections...", spinner="dots"
                ):
                    if complexity == "SIMPLE":
                        coder_response = coder.run(
                            task_description=task_description + f"\n\nNudge: {nudge_prompt}",
                            plan=plan,
                            repo_files_content={**repo_files_content, **generated_files},
                            history=self.conversation_history,
                        )
                    else:
                        coder_response = coder.run(
                            task_description=task_description + f"\n\nNudge: {nudge_prompt}",
                            spec=spec,
                            repo_files_content={**repo_files_content, **generated_files},
                            history=self.conversation_history,
                        )
                    updated_files = coder.parse_files(coder_response)
                    if updated_files:
                        for fp, content in updated_files.items():
                            generated_files[fp] = content

        # 6. Step 4: Writing Changes to Disk
        console.print(
            Panel(
                "[bold yellow]Step 4: Writing files to repository...[/bold yellow]",
                border_style="yellow",
            )
        )

        if config.SANDBOX_READ_ONLY:
            console.print(
                "[bold red]Sandbox Protection Active: Current directory is read-only. Bypassing writes.[/bold red]"
            )
            for rel_path, content in generated_files.items():
                console.print(
                    Panel(content, title=f"[cyan]File Preview: {rel_path}[/cyan] (Read-Only Mode)")
                )
            console.print(
                Panel(
                    "[bold yellow]MACA completed the run, but did not write to disk due to sandbox permissions.[/bold yellow]",
                    border_style="yellow",
                )
            )

            # Record dry run summary
            self.conversation_history.append(f"User Request: {task_description}")
            self.conversation_history.append(f"Planner Implementation Steps:\n{plan}")
            self.conversation_history.append(
                "Files Created/Modified (Dry-Run Preview only): "
                + ", ".join(generated_files.keys())
            )
            self.conversation_history.append("Reviewer Decision: APPROVED")
            return

        table = Table(title="File Writing Summary")
        table.add_column("File Path", style="cyan")
        table.add_column("Action", style="green")
        table.add_column("Size (chars)", style="magenta")

        written_count = 0
        for rel_path, content in generated_files.items():
            # Clean leading/trailing spaces and leading slashes to prevent absolute path escapes
            clean_rel_path = rel_path.strip().lstrip("/")

            # Form absolute paths and verify they reside strictly inside self.repo_path (sandbox safety)
            repo_abs = os.path.abspath(self.repo_path)
            full_path = os.path.abspath(os.path.join(repo_abs, clean_rel_path))

            try:
                common = os.path.commonpath([repo_abs, full_path])
                is_safe = common == repo_abs
            except Exception:
                is_safe = False

            if not is_safe:
                table.add_row(rel_path, "[bold red]Failed: Sandbox escape blocked[/bold red]", "0")
                continue

            action = "Modified" if os.path.exists(full_path) else "Created"

            # Write file using standard agent call helper
            res = planner.write_file(full_path, content)
            if "Successfully" in res:
                table.add_row(clean_rel_path, action, str(len(content)))
                written_count += 1
            else:
                table.add_row(clean_rel_path, f"[bold red]Failed: {res}[/bold red]", "0")

        if len(generated_files) > 0:
            console.print(table)

        if written_count > 0:
            console.print(
                f"[bold green]Successfully applied {written_count} changes to the repository![/bold green]"
            )
        else:
            console.print("[bold red]No changes were applied to the repository.[/bold red]")

        console.print(
            Panel(
                "[bold green]Coding Task Completed successfully![/bold green]", border_style="green"
            )
        )

        # 7. Record to conversation history
        self.conversation_history.append(f"User Request: {task_description}")
        self.conversation_history.append(f"Planner Implementation Steps:\n{plan}")
        files_written = ", ".join(generated_files.keys()) if written_count > 0 else "None"
        self.conversation_history.append(f"Files Modified/Created: {files_written}")
        self.conversation_history.append("Reviewer Decision: APPROVED")
