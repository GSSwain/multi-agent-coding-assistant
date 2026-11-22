from typing import Any, Dict, List, Optional

from maca.rich_compat import Console, Markdown, Panel, Table

console = Console()


class OrchestratorDisplay:
    """Manages CLI presentation and Rich formatting for MACA Orchestrator."""

    def __init__(self, console_instance: Optional[Console] = None):
        self.console = console_instance or console

    def show_task_header(self, task: str, repo_path: str, allowed_directory: str):
        self.console.print(
            Panel(
                f"[bold blue]Multi-Agent Coding Assistant[/bold blue]\n"
                f"[bold white]Workspace (Modifiable):[/bold white] {repo_path}\n"
                f"[bold white]Allowed Directory (Read-Only):[/bold white] {allowed_directory}\n"
                f"[bold white]Task:[/bold white] {task}",
                border_style="blue",
            )
        )

    def show_complexity(self, complexity: str):
        self.console.print(
            f"[bold green]Task Complexity Evaluated:[/bold green] [bold cyan]{complexity}[/bold cyan]"
        )

    def show_bootstrap_config(self, bootstrap_config: Dict[str, str]):
        table = Table(title="[bold green]Resolved Framework Bootstrap Configuration[/bold green]")
        table.add_column("Parameter", style="cyan")
        table.add_column("Selection", style="green")
        for key, val in bootstrap_config.items():
            table.add_row(key.replace("_", " ").title(), str(val))
        self.console.print(table)

    def show_model_selection(self, model_name: str, model_override: Optional[str] = None):
        if model_override:
            self.console.print(
                f"[bold yellow]Model override active:[/bold yellow] [bold cyan]{model_name}[/bold cyan]"
            )
        self.console.print(
            f"[bold green]Selected Model Client:[/bold green] [bold cyan]{model_name}[/bold cyan]\n"
        )

    def show_step_header(self, title: str, subtitle: Optional[str] = None):
        body = f"[bold yellow]{title}[/bold yellow]"
        if subtitle:
            body += f"\n[cyan]{subtitle}[/cyan]"
        self.console.print(Panel(body, border_style="yellow"))

    def show_plan(self, plan: str, plan_file_path: str):
        self.console.print(
            Panel(
                Markdown(plan),
                title="[bold green]Implementation Plan[/bold green]",
                border_style="green",
            )
        )
        self.console.print(f"[bold green]Plan saved to {plan_file_path}[/bold green]")

    def show_spec(self, spec: str, spec_file_path: str):
        self.console.print(
            Panel(
                Markdown(spec),
                title="[bold green]Technical Specification[/bold green]",
                border_style="green",
            )
        )
        self.console.print(f"[bold green]Spec saved to {spec_file_path}[/bold green]")

    def show_generated_files(self, generated_files: Dict[str, str], raw_response: str):
        if not generated_files:
            self.console.print(
                "[bold red]Warning: Coder did not output any files in the expected format [FILE: path]...[/bold red]"
            )
            self.console.print("[yellow]Raw coder response structure check:[/yellow]")
            self.console.print(raw_response[:500] + "...")
        else:
            self.console.print(
                f"[bold green]Coder generated {len(generated_files)} files:[/bold green]"
            )
            for fp in generated_files.keys():
                self.console.print(f" - [cyan]{fp}[/cyan]")

    def show_pre_review_files(
        self,
        summary_records: List[Dict[str, str]],
        generated_files: Dict[str, str],
        sandbox_read_only: bool,
    ):
        if sandbox_read_only:
            self.console.print(
                "[bold red]Sandbox Protection Active: Current directory is read-only. Previewing writes.[/bold red]"
            )
            for rel_path, content in generated_files.items():
                self.console.print(
                    Panel(content, title=f"[cyan]File Preview: {rel_path}[/cyan] (Read-Only Mode)")
                )
        else:
            table = Table(title="Generated Code Files Staged (Pre-Review)")
            table.add_column("File Path", style="cyan")
            table.add_column("Action", style="green")
            table.add_column("Size (chars)", style="magenta")
            for rec in summary_records:
                table.add_row(rec["path"], rec["action"], rec["size"])
            if len(generated_files) > 0:
                self.console.print(table)

    def show_review_report(self, report: str, attempt: int):
        self.console.print(
            Panel(
                Markdown(report),
                title=f"[bold green]Reviewer Report (Attempt {attempt})[/bold green]",
                border_style="green",
            )
        )

    def show_promoted_files(
        self,
        summary_records: List[Dict[str, Any]],
        repo_path: str,
        sandbox_read_only: bool,
    ):
        self.show_step_header(
            f"Step 3.5: Promoting approved code changes from staging to target directory ({repo_path})..."
        )
        if sandbox_read_only:
            self.console.print(
                "[bold yellow]Dry-Run Mode: Staged files were not promoted to target directory due to read-only sandbox.[/bold yellow]"
            )
            return

        table = Table(title="Approved Code Files Moved to Target Directory (Post-Review)")
        table.add_column("Target File Path", style="cyan")
        table.add_column("Action", style="green")
        table.add_column("Size (chars)", style="magenta")
        for rec in summary_records:
            table.add_row(rec["path"], f"Promoted ({rec['action']})", rec["size"])
        if summary_records:
            self.console.print(table)
            self.console.print(
                f"[bold green]✓ Moved {len(summary_records)} approved file(s) from staging into {repo_path}[/bold green]"
            )

    def show_task_completed(self, is_dry_run: bool = False):
        if is_dry_run:
            self.console.print(
                Panel(
                    "[bold yellow]MACA completed the run, but did not write to disk due to sandbox permissions.[/bold yellow]",
                    border_style="yellow",
                )
            )
        else:
            self.console.print(
                Panel(
                    "[bold green]Coding Task Completed successfully![/bold green]",
                    border_style="green",
                )
            )
