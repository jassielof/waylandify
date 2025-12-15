"""
Command-line interface for waylandify.

This module provides the CLI commands for managing Wayland flags
in desktop files for Chromium-based applications.
"""

from importlib.metadata import version
from typing import Annotated

import typer
from rich import print

from .commands.apply import app as apply_app
from .commands.clean import app as clean_app
from .commands.diff import app as diff_app
from .commands.init import app as init_app
from .commands.list_programs import app as list_programs_app
from .commands.prune import app as prune_app
from .commands.restore import app as restore_app
from .commands.status import app as status_app
from .commands.validate import app as validate_app
from .commands.verify import app as verify_app

app = typer.Typer(
    help="A CLI tool to apply Wayland flags to Chromium-based applications.",
    no_args_is_help=True,
)

app.add_typer(apply_app)
app.add_typer(diff_app)
app.add_typer(clean_app)
app.add_typer(list_programs_app)
app.add_typer(prune_app)
app.add_typer(restore_app)
app.add_typer(status_app)
app.add_typer(validate_app)
app.add_typer(verify_app)
app.add_typer(init_app)


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        print(f"[bold cyan]waylandify[/bold cyan] {version('waylandify')}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """
    Waylandify - Add Wayland support to Chromium-based applications.

    Automatically modifies .desktop files to enable Wayland support without touching system files.
    """
    pass
