from pathlib import Path

import typer
from rich import print
from rich.table import Table
from typing_extensions import Annotated

from cli import backup

app = typer.Typer()


@app.command()
def restore(
    backup_id: Annotated[
        str | None,
        typer.Argument(
            help="Backup directory name to restore from (e.g., backup_20240101_120000_123456)"
        ),
    ] = None,
    remove_only: Annotated[
        bool,
        typer.Option(
            "--remove-only",
            "-r",
            help="Remove modified desktop files without restoring backups (reverts to system defaults)",
        ),
    ] = False,
):
    """
    Restore desktop files from a backup or revert to system defaults.

    Without arguments, lists available backups.
    With --remove-only, removes user desktop files to use system defaults.
    With a backup ID, restores files from that specific backup.

    Examples:
        $ waylandify restore                        # List backups
        $ waylandify restore backup_20240101_120000 # Restore specific backup
        $ waylandify restore --remove-only          # Remove all modified files
    """
    if remove_only:
        print("[bold yellow]Removing modified desktop files...[/bold yellow]")
        count = backup.remove_user_desktop_files()
        if count > 0:
            print(
                f"\n[bold green]✨ Removed {count} file(s). System will now use default desktop files.[/bold green]"
            )
        else:
            print("[dim]No modified desktop files found.[/dim]")
        return

    if backup_id is None:
        backups = backup.list_backups()

        if not backups:
            print("[dim]No backups found.[/dim]")
            print("\nTo create backups, run: [cyan]waylandify apply[/cyan]")
            return

        # Group backups by backup_dir
        backup_dirs: dict[str, list] = {}
        for b in backups:
            dir_name = Path(b["backup_dir"]).name
            if dir_name not in backup_dirs:
                backup_dirs[dir_name] = []
            backup_dirs[dir_name].append(b)

        table = Table(
            title="Available Backups", show_header=True, header_style="bold magenta"
        )
        table.add_column("Backup ID", style="cyan")
        table.add_column("Date/Time", style="green")
        table.add_column("Files", justify="right", style="yellow")

        for dir_name, backup_list in sorted(backup_dirs.items(), reverse=True):
            try:
                timestamp_str = dir_name.replace("backup_", "")
                date_part = timestamp_str[:8]
                time_part = timestamp_str[9:15]
                formatted = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            except Exception:
                formatted = timestamp_str

            table.add_row(dir_name, formatted, str(len(backup_list)))

        print(table)
        print("\nTo restore: [cyan]waylandify restore <backup_id>[/cyan]")
        print("To remove all: [cyan]waylandify restore --remove-only[/cyan]")
        return

    backup_dir_path = backup.BACKUP_DIR / backup_id

    if not backup_dir_path.exists():
        print(f"[bold red]❌ Backup not found: {backup_id}[/bold red]")
        print("\nRun [cyan]waylandify restore[/cyan] to see available backups.")
        raise typer.Exit(code=1)

    print(f"[bold yellow]Restoring from backup: {backup_id}[/bold yellow]")
    success = backup.restore_from_backup(backup_dir_path)

    if success:
        print("\n[bold green]✨ Restore completed successfully![/bold green]")
    else:
        print("\n[bold red]❌ Restore completed with errors.[/bold red]")
        raise typer.Exit(code=1)
