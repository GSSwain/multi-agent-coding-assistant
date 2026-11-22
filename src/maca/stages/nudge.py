from typing import Any, Callable, Dict, Optional, Tuple

from maca.rich_compat import Console

console = Console()


class NudgeLoopRunner:
    """Encapsulates the nudge iteration execution against the coder agent."""

    @staticmethod
    def run_nudge_iteration(
        run_coder_fn: Callable[..., Tuple[Dict[str, str], Any, str]],
        apply_update_fn: Callable[..., Dict[str, Any]],
        nudge_prompt: str,
        nudge_label: str,
        spinner_message: str,
        persist_changes: bool,
        **coder_kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Executes a single nudge iteration against the coder agent and applies file updates."""
        console.print(f"[bold yellow]Nudging Coder Agent to {nudge_label}...[/bold yellow]")
        with console.status(f"[bold yellow]{spinner_message}", spinner="dots"):
            updated_files, _, _ = run_coder_fn(**coder_kwargs, nudge=nudge_prompt)
            if updated_files:
                return apply_update_fn(
                    updated_files=updated_files,
                    summary_label=nudge_label,
                    persist_changes=persist_changes,
                )
        return None
