import os
import sys
import argparse

# Inject package root directory to allow standalone execution
package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_root not in sys.path:
    sys.path.append(package_root)

from maca.rich_compat import Console, Panel, Prompt, Table
from maca import maca_config as config
from maca.orchestrator import Orchestrator

console = Console()

def display_welcome(orch=None):
    welcome_text = (
        "[bold cyan]Welcome to the Multi-Agent Coding Assistant (MACA)![/bold cyan]\n"
        "MACA classifies your coding task complexity and routes it to the best model:\n"
        " - [bold green]Simple Complexity[/bold green] -> [bold cyan]Local Gemma[/bold cyan] (via Ollama)\n"
        " - [bold yellow]Medium/Complex/Very Complex Complexity[/bold yellow] -> [bold cyan]Google Gemini[/bold cyan] (via API)\n\n"
        "Type your task prompt directly, or use special slash commands:\n"
        " - [bold magenta]/exit[/bold magenta] or [bold magenta]/quit[/bold magenta]: Exit the assistant\n"
        " - [bold magenta]/status[/bold magenta]: Run live connection checks on all models\n"
        " - [bold magenta]/model <name>[/bold magenta]: Override default model (options: gemma, gemini, auto)\n"
        " - [bold magenta]/help[/bold magenta]: Show this help message"
    )
    console.print(Panel(welcome_text, title="[bold white]MACA CLI v1.0.0-alpha[/bold white]", border_style="cyan"))
    
    if orch:
        print_backends_status(orch, run_handshakes=False)

def print_backends_status(orch, run_handshakes=False):
    title = "Backend Connectivity (Live Handshakes)" if run_handshakes else "Backend Connectivity (Fast Check)"
    with console.status("[bold yellow]Checking backends...", spinner="dots") if run_handshakes else console.status("[bold yellow]Checking config...", spinner="dots") as s:
        status_dict = orch.check_backends_status(run_handshakes=run_handshakes)
        
    table = Table(title=title)
    table.add_column("Backend Model", style="cyan")
    table.add_column("Connectivity Status", style="magenta")
    
    for name, stat in status_dict.items():
        style_color = "green" if "ONLINE" in stat or "CONFIGURED" in stat else "red"
        if "OFFLINE" in stat:
            style_color = "yellow"
        table.add_row(name, f"[{style_color}]{stat}[/{style_color}]")
        
    console.print(table)

def contains_filename_or_project(prompt):
    prompt_lower = prompt.lower()
    
    # Check for common extensions
    extensions = [".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".sh", ".java", ".cpp", ".h", ".cs", ".go", ".rs", ".yml", ".yaml", ".txt"]
    if any(ext in prompt_lower for ext in extensions):
        return True
        
    # Clean up punctuation and split
    clean_prompt = prompt_lower.replace(",", " ").replace(".", " ").replace("?", " ").replace("!", " ")
    words = clean_prompt.split()
    keywords = {"file", "project", "folder", "directory", "repo", "repository"}
    if any(w in keywords for w in words):
        return True
            
    return False

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Coding Assistant (MACA)")
    parser.add_argument("task", nargs="?", default=None, help="The coding task description")
    parser.add_argument("--repo", default=".", help="Target repository directory path")
    parser.add_argument("--model", default=None, choices=["gemma", "gemini"], help="Force a specific model")
    parser.add_argument("--mock", action="store_true", help="Force local Gemma simulated mode")
    args = parser.parse_args()

    # 1. Print CWD
    repo_path = os.path.abspath(args.repo)
    console.print(f"[bold cyan]Current Working Directory:[/bold cyan] {os.getcwd()}")
    console.print(f"[bold cyan]Target Repository Path:[/bold cyan] {repo_path}")

    # 2. Confirm Access
    try:
        confirm = Prompt.ask(
            f"[bold yellow]Do you grant MACA permission to access and modify files in this path? (y/n)[/bold yellow]",
            choices=["y", "n"],
            default="y"
        )
        if confirm.lower() != "y":
            console.print("[bold red]Access denied by user. Safe exit.[/bold red]")
            sys.exit(0)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold red]Safe exit.[/bold red]")
        sys.exit(0)

    # 3. Verify Read/Write Access (Sandbox verification check)
    try:
        # Test read
        os.listdir(repo_path)
        # Test write
        test_file = os.path.join(repo_path, ".maca_sandbox_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        
        console.print("[bold green]✓ Sandbox check: Read/Write access verified successfully.[/bold green]\n")
    except Exception as e:
        config.SANDBOX_READ_ONLY = True
        console.print(
            f"[bold red]Sandbox Alert: Target directory is restricted or read-only ({e}).[/bold red]\n"
            "[bold yellow]MACA will run safely in Dry-Run mode (code will be generated and previewed, but not written to disk).[/bold yellow]\n"
        )

    if args.mock:
        config.MOCK_GEMMA_FALLBACK = True
        console.print("[bold yellow]Mock mode forced: Gemma/Gemini will run in simulation mode.[/bold yellow]\n")

    orch = Orchestrator(args.repo)

    # Run direct command if provided
    if args.task:
        try:
            task_description = args.task
            if not contains_filename_or_project(task_description):
                target = Prompt.ask("[bold yellow]No file name or project specified. Target file/folder name:[/bold yellow]")
                if target.strip():
                    task_description += f" (Target: {target.strip()})"
                    
            orch.run_task(task_description, model_override=args.model)
        except Exception as e:
            console.print(f"[bold red]Error running task: {e}[/bold red]")
        return

    # Interactive REPL mode
    display_welcome(orch)
    model_override = args.model

    while True:
        try:
            model_indicator = f" ({model_override})" if model_override else " (auto)"
            prompt = Prompt.ask(f"[bold green]MACA{model_indicator} >[/bold green]")
            
            # Check empty prompt
            if not prompt.strip():
                continue
                
            # Handle commands
            if prompt.strip().startswith("/"):
                parts = prompt.strip().split()
                cmd = parts[0].lower()
                
                if cmd in ["/exit", "/quit"]:
                    console.print("[bold cyan]Goodbye![/bold cyan]")
                    break
                elif cmd == "/help":
                    display_welcome(orch)
                elif cmd == "/status":
                    print_backends_status(orch, run_handshakes=True)
                elif cmd == "/model":
                    if len(parts) > 1:
                        val = parts[1].lower()
                        if val in ["gemma", "gemini"]:
                            model_override = val
                            console.print(f"[bold green]Model override set to {val.upper()}[/bold green]")
                        elif val == "auto":
                            model_override = None
                            console.print("[bold green]Model routing set to AUTO (based on complexity)[/bold green]")
                        else:
                            console.print("[bold red]Invalid model. Options: gemma, gemini, auto[/bold red]")
                    else:
                        console.print("[bold red]Usage: /model <gemma|gemini|auto>[/bold red]")
                else:
                    console.print(f"[bold red]Unknown command: {cmd}[/bold red]")
                continue
                
            # Check if task description has file name/project folder
            task_description = prompt
            if not contains_filename_or_project(task_description):
                target = Prompt.ask("[bold yellow]No file name or project specified. Target file/folder name:[/bold yellow]")
                if target.strip():
                    task_description += f" (Target: {target.strip()})"
                    
            # Run the task
            orch.run_task(task_description, model_override=model_override)
            
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold cyan]Goodbye![/bold cyan]")
            break
        except Exception as e:
            console.print(f"[bold red]Error processing request: {e}[/bold red]")
            console.print("[yellow]Continuing session...[/yellow]")

if __name__ == "__main__":
    main()
