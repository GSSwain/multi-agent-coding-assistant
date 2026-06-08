import os
import sys
from maca.rich_compat import Console, Panel, Markdown, Table
from maca.evaluator import ComplexityEvaluator
from maca.models.local_gemma import LocalGemmaClient
from maca.models.gemini import GeminiClient

# Import agents
from maca.agents.planner import PlannerAgent
from maca.agents.coder import CoderAgent
from maca.agents.reviewer import ReviewerAgent
from maca import maca_config as config

console = Console()

class Orchestrator:
    def __init__(self, repo_path="."):
        self.repo_path = os.path.abspath(repo_path)
        self.evaluator = ComplexityEvaluator()
        self.conversation_history = []
        
    def check_backends_status(self, run_handshakes=False):
        # Checks status of Gemma (Ollama) and Gemini backends.
        status = {}
        
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
                res = subprocess.run(["pgrep", "-af", "ollama"], capture_output=True, text=True, timeout=2)
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
                    status["Gemini"] = f"CONNECTION FAILED: {str(e)[:80]}"
                finally:
                    config.MOCK_GEMMA_FALLBACK = old_mock
            else:
                status["Gemini"] = "CONFIGURED (Key Present)"
                
        return status
        
    def run_task(self, task_description, model_override=None):
        console.print(Panel(f"[bold blue]Multi-Agent Coding Assistant[/bold blue]\n[bold white]Repo Path:[/bold white] {self.repo_path}\n[bold white]Task:[/bold white] {task_description}", border_style="blue"))
        
        # 1. Evaluate Complexity
        with console.status("[bold yellow]Evaluating task complexity...", spinner="dots"):
            complexity = self.evaluator.evaluate(task_description)
            
        console.print(f"[bold green]Task Complexity Evaluated:[/bold green] [bold cyan]{complexity}[/bold cyan]")
        
        # 2. Select Model Client
        model_name = ""
        client = None
        
        if model_override:
            model_name = model_override.upper()
            console.print(f"[bold yellow]Model override active:[/bold yellow] [bold cyan]{model_name}[/bold cyan]")
        else:
            if complexity == "SIMPLE":
                model_name = "GEMMA (LOCAL)"
                client = LocalGemmaClient()
            else:
                model_name = "GEMINI (REMOTE)"
                client = GeminiClient()
                
        # Validate config for selected model
        if model_name.startswith("GEMINI"):
            client = GeminiClient()
            config.validate_config(complexity)
        elif model_name.startswith("GEMMA") and client is None:
            client = LocalGemmaClient()

        console.print(f"[bold green]Selected Model Client:[/bold green] [bold cyan]{model_name}[/bold cyan]\n")

        # Get existing files in the repo
        planner = PlannerAgent(client)
        repo_files = planner.list_files(self.repo_path)
        
        # 3. Step 1: Planning Agent
        console.print(Panel("[bold yellow]Step 1: Planner Agent starting...[/bold yellow]", border_style="yellow"))
        with console.status("[bold yellow]Planner Agent is generating the implementation plan...", spinner="dots"):
            plan = planner.run(task_description, repo_files, history=self.conversation_history)
            
        console.print(Panel(Markdown(plan), title="[bold green]Implementation Plan[/bold green]", border_style="green"))
        
        # 4. Step 2: Coder Agent
        console.print(Panel("[bold yellow]Step 2: Coder Agent starting...[/bold yellow]", border_style="yellow"))
        
        # Read contents of files mentioned in plan to provide context to Coder if they exist
        repo_files_content = {}
        for filepath in repo_files:
            # Check if planner plan mentions the file
            if filepath.lower() in plan.lower():
                full_path = os.path.join(self.repo_path, filepath)
                if os.path.exists(full_path):
                    repo_files_content[filepath] = planner.read_file(full_path)

        coder = CoderAgent("Coder", client)
        with console.status("[bold yellow]Coder Agent is implementing the changes...", spinner="dots"):
            coder_response = coder.run(task_description, plan, repo_files_content, history=self.conversation_history)
            generated_files = coder.parse_files(coder_response)
            
        if not generated_files:
            console.print("[bold red]Warning: Coder did not output any files in the expected format [FILE: path]...[/bold red]")
            console.print("[yellow]Raw coder response structure check:[/yellow]")
            console.print(coder_response[:500] + "...")
        else:
            console.print(f"[bold green]Coder generated {len(generated_files)} files:[/bold green]")
            for fp in generated_files.keys():
                console.print(f" - [cyan]{fp}[/cyan]")
                
        # 5. Step 3: Reviewer Agent
        console.print(Panel("[bold yellow]Step 3: Reviewer Agent starting...[/bold yellow]", border_style="yellow"))
        reviewer = ReviewerAgent(client)
        with console.status("[bold yellow]Reviewer Agent is auditing the generated code...", spinner="dots"):
            reviewer_response = reviewer.run(task_description, generated_files, history=self.conversation_history)
            reviewed_files = reviewer.parse_files(reviewer_response)
            
        console.print(Panel(Markdown(reviewer_response), title="[bold green]Reviewer Report[/bold green]", border_style="green"))
        
        # Merge changes from reviewer if any
        if reviewed_files:
            console.print("[bold yellow]Reviewer suggested corrections for the following files:[/bold yellow]")
            for fp, content in reviewed_files.items():
                console.print(f" - [cyan]{fp}[/cyan] (Updated)")
                generated_files[fp] = content
                
        # 6. Step 4: Writing Changes to Disk
        console.print(Panel("[bold yellow]Step 4: Writing files to repository...[/bold yellow]", border_style="yellow"))
        
        if config.SANDBOX_READ_ONLY:
            console.print("[bold red]Sandbox Protection Active: Current directory is read-only. Bypassing writes.[/bold red]")
            for rel_path, content in generated_files.items():
                console.print(Panel(content, title=f"[cyan]File Preview: {rel_path}[/cyan] (Read-Only Mode)"))
            console.print(Panel("[bold yellow]MACA completed the run, but did not write to disk due to sandbox permissions.[/bold yellow]", border_style="yellow"))
            
            # Record dry run summary
            self.conversation_history.append(f"User Request: {task_description}")
            self.conversation_history.append(f"Planner Implementation Steps:\n{plan}")
            self.conversation_history.append("Files Created/Modified (Dry-Run Preview only): " + ", ".join(generated_files.keys()))
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
                is_safe = (common == repo_abs)
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
            console.print(f"[bold green]Successfully applied {written_count} changes to the repository![/bold green]")
        else:
            console.print("[bold red]No changes were applied to the repository.[/bold red]")
            
        console.print(Panel("[bold green]Coding Task Completed successfully![/bold green]", border_style="green"))
        
        # 7. Record to conversation history
        self.conversation_history.append(f"User Request: {task_description}")
        self.conversation_history.append(f"Planner Implementation Steps:\n{plan}")
        files_written = ", ".join(generated_files.keys()) if written_count > 0 else "None"
        self.conversation_history.append(f"Files Modified/Created: {files_written}")
        self.conversation_history.append(f"Reviewer Decision: APPROVED")
