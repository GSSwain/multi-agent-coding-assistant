import sys

GREEN = "\\033[92m"
YELLOW = "\\033[93m"
RED = "\\033[91m"
BLUE = "\\033[94m"
MAGENTA = "\\033[95m"
CYAN = "\\033[96m"
BOLD = "\\033[1m"
WHITE = "\\033[97m"
RESET = "\\033[0m"

def clean_tags(text):
    if not isinstance(text, str):
        return str(text)
    text = text.replace("[bold blue]", BOLD + BLUE)
    text = text.replace("[/bold blue]", RESET)
    text = text.replace("[bold white]", BOLD + WHITE)
    text = text.replace("[/bold white]", RESET)
    text = text.replace("[bold green]", BOLD + GREEN)
    text = text.replace("[/bold green]", RESET)
    text = text.replace("[bold yellow]", BOLD + YELLOW)
    text = text.replace("[/bold yellow]", RESET)
    text = text.replace("[bold red]", BOLD + RED)
    text = text.replace("[/bold red]", RESET)
    text = text.replace("[bold magenta]", BOLD + MAGENTA)
    text = text.replace("[/bold magenta]", RESET)
    text = text.replace("[bold cyan]", BOLD + CYAN)
    text = text.replace("[/bold cyan]", RESET)
    text = text.replace("[cyan]", CYAN)
    text = text.replace("[/cyan]", RESET)
    text = text.replace("[yellow]", YELLOW)
    text = text.replace("[/yellow]", RESET)
    text = text.replace("[magenta]", MAGENTA)
    text = text.replace("[/magenta]", RESET)
    return text

class ConsoleShim:
    def print(self, *args, **kwargs):
        cleaned_args = [clean_tags(arg) for arg in args]
        # For Rich Panel or other class outputs
        final_args = []
        for arg in cleaned_args:
            if hasattr(arg, "__str__"):
                final_args.append(str(arg))
            else:
                final_args.append(arg)
        print(*final_args, **kwargs)

    def status(self, text, spinner="dots"):
        class StatusContext:
            def __init__(self, text):
                self.text = text
            def __enter__(self):
                print(clean_tags(f"{YELLOW}* {self.text}...{RESET}"))
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        return StatusContext(text)

class PanelShim:
    def __init__(self, text, title=None, border_style=None):
        self.text = text
        self.title = title
        self.border_style = border_style

    def __str__(self):
        title_str = f" {self.title} " if self.title else ""
        border_char = "="
        header = f"{border_char * 10}{title_str}{border_char * 30}"
        footer = border_char * len(header)
        return clean_tags(f"\\n{header}\\n{self.text}\\n{footer}\\n")

class MarkdownShim:
    def __init__(self, text):
        self.text = text
    def __str__(self):
        return self.text

class TableShim:
    def __init__(self, title=None):
        self.title = title
        self.columns = []
        self.rows = []
    def add_column(self, name, style=None):
        self.columns.append(name)
    def add_row(self, *args):
        self.rows.append(args)
    def __str__(self):
        res = f"\\n--- {self.title} ---\\n" if self.title else "\\n"
        res += " | ".join(self.columns) + "\\n"
        res += "-" * (sum(len(c) for c in self.columns) + 3 * len(self.columns)) + "\\n"
        for r in self.rows:
            res += " | ".join(r) + "\\n"
        return res

class PromptShim:
    @staticmethod
    def ask(prompt="", *, console=None, default=None, choices=None, show_default=True, show_choices=True, password=False):
        import getpass
        cleaned = clean_tags(prompt)
        
        suffix = ""
        if choices and show_choices:
            choice_str = ", ".join(choices)
            if not (choice_str in prompt or "/".join(choices) in prompt):
                suffix += f" [{choice_str}]"
        if default is not None and show_default:
            if str(default) not in prompt:
                suffix += f" ({default})"
                
        prompt_str = cleaned + suffix + " "
        
        while True:
            try:
                if password:
                    res = getpass.getpass(prompt_str)
                else:
                    res = input(prompt_str)
            except (KeyboardInterrupt, EOFError):
                raise
                
            if not res.strip():
                if default is not None:
                    return default
                continue
                
            val = res.strip()
            if choices:
                if val in choices:
                    return val
                else:
                    print(f"Please select one of: {', '.join(choices)}")
                    continue
            return val
