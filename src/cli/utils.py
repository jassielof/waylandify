import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from cli import config, discovery


def _load_config_or_exit() -> config.Config:
    """Load config and exit with error message if it fails."""
    try:
        return config.load_config()
    except FileNotFoundError:
        print(
            "[bold red]Config file not found. Run 'waylandify init' first.[/bold red]"
        )
        raise typer.Exit(code=1)
    except Exception:
        raise typer.Exit(code=1)


def _create_indexer() -> discovery.DesktopFileIndexer:
    """Create a desktop file indexer with a progress spinner."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Indexing desktop files...", total=None)
        return discovery.DesktopFileIndexer()
