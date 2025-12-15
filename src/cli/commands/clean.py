from typing import Annotated

import typer
from rich import print

from cli import backup

app = typer.Typer()


@app.command()
def clean(
    older_than: Annotated[
        int | None,
        typer.Option(
            "--older-than",
            "-d",
            help="Remove backups older than N days.",
        ),
    ] = None,
    all_backups: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Remove all backups.",
        ),
    ] = False,
):
    """
    Clean up old backup files.

    Remove backup files to free up disk space. You can remove
    all backups or only those older than a certain number of days.

    Examples:
        $ waylandify clean                  # Show backup stats
        $ waylandify clean --older-than 30  # Remove backups older than 30 days
        $ waylandify clean --all            # Remove all backups
    """
    if not all_backups and older_than is None:
        stats = backup.get_backup_stats()

        if stats["total_backups"] == 0 and stats["total_modifications"] == 0:
            print("[dim]No backups or tracked modifications found.[/dim]")
            return

        print("[bold]Backup Statistics[/bold]\n")
        print(f"  📦 Backup entries: {stats['total_backups']}")
        print(f"  📁 Backup directories: {stats['total_dirs']}")
        print(f"  📝 Tracked modifications: {stats['total_modifications']}")

        if stats["oldest"]:
            print(f"  📅 Oldest: {stats['oldest'].strftime('%Y-%m-%d %H:%M:%S')}")
        if stats["newest"]:
            print(f"  📅 Newest: {stats['newest'].strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"\n  📍 Location: {backup.BACKUP_DIR}")
        print("\n[dim]Use --older-than N or --all to remove backups.[/dim]")
        return

    if all_backups:
        confirm = typer.confirm("Permanently delete ALL backups?")
        if not confirm:
            print("[dim]Cancelled.[/dim]")
            return

        if backup.clear_all_backups():
            print("\n[bold green]✨ All backups removed.[/bold green]")
        else:
            raise typer.Exit(code=1)
        return

    if older_than is not None:
        if older_than < 1:
            print("[bold red]❌ --older-than must be at least 1 day.[/bold red]")
            raise typer.Exit(code=1)

        print(
            f"[bold yellow]Removing backups older than {older_than} day(s)...[/bold yellow]"
        )
        dirs_removed, files_removed = backup.clean_old_backups(older_than)

        if dirs_removed > 0:
            print(f"\n[bold green]✨ Removed {dirs_removed} backup(s).[/bold green]")
        else:
            print(f"\n[dim]No backups older than {older_than} day(s).[/dim]")
