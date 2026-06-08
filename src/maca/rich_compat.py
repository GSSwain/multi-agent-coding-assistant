try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.status import Status
    from rich.prompt import Prompt
except ImportError:
    from maca.rich_shim import ConsoleShim as Console
    from maca.rich_shim import PanelShim as Panel
    from maca.rich_shim import MarkdownShim as Markdown
    from maca.rich_shim import TableShim as Table
    from maca.rich_shim import PromptShim as Prompt
