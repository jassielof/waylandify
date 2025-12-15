from pathlib import Path

import typer
from rich import print
from typing_extensions import Annotated

from cli import backup, config
from cli.utils import _create_indexer

app = typer.Typer()


@app.command()
def prune(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be removed without actually removing anything.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Remove orphan files without confirmation.",
        ),
    ] = False,
):
    """
    Remove orphan desktop files from uninstalled applications.

    Detects and removes desktop files in ~/.local/share/applications
    whose executables no longer exist (application was uninstalled).

    This is useful when:
    - You uninstall an application (like Vivaldi or a PWA)
    - The modified desktop file remains in ~/.local/share/applications
    - The system no longer has the original desktop file

    Examples:
        $ waylandify prune --dry-run  # Preview what would be removed
        $ waylandify prune            # Remove orphans (with confirmation)
        $ waylandify prune --force    # Remove orphans without confirmation
    """
    if dry_run:
        print("[bold yellow]Dry-run mode: No files will be removed.[/bold yellow]\n")

    indexer = _create_indexer()
    user_desktop_dir = config.get_user_desktop_dir()

    # Get all system desktop file names (excluding user directory)
    system_desktop_files: set[str] = set()
    for directory in indexer.desktop_file_dirs:
        # Exclude user directory - we're looking for system-installed files
        if directory == user_desktop_dir:
            continue
        if directory.is_dir():
            for desktop_file in directory.glob("*.desktop"):
                system_desktop_files.add(desktop_file.name)

    # Find all orphan desktop files in user directory
    all_orphans: list[dict] = []
    tracked_modifications = {
        Path(m["target_path"]).name: m for m in backup.get_modified_files()
    }

    if user_desktop_dir.exists():
        for desktop_file in user_desktop_dir.glob("*.desktop"):
            # Skip if the file exists in system directories (not an orphan)
            if desktop_file.name in system_desktop_files:
                continue

            # Check if the executable exists
            if not backup._check_executable_exists(desktop_file):
                # Check if we have tracking info for this file
                if desktop_file.name in tracked_modifications:
                    mod_info = tracked_modifications[desktop_file.name]
                    all_orphans.append(
                        {
                            "target_path": str(desktop_file),
                            "source_path": mod_info.get(
                                "source_path", str(desktop_file)
                            ),
                            "program_name": mod_info.get("program_name", "Unknown"),
                            "reason": "Executable not found",
                        }
                    )
                else:
                    all_orphans.append(
                        {
                            "target_path": str(desktop_file),
                            "source_path": str(desktop_file),
                            "program_name": "Untracked",
                            "reason": "Executable not found",
                        }
                    )

    if not all_orphans:
        print("[bold green]✨ No orphan desktop files found.[/bold green]")
        return

    print(
        f"[bold yellow]Found {len(all_orphans)} orphan desktop file(s):[/bold yellow]\n"
    )

    for orphan in all_orphans:
        target_path = Path(orphan["target_path"])
        print(f"  🗑️  [cyan]{target_path.name}[/cyan]")
        print(f"      [dim]Program: {orphan.get('program_name', 'Unknown')}[/dim]")
        print(f"      [dim]Reason: {orphan.get('reason', 'Source not found')}[/dim]")

    print()

    if dry_run:
        print(f"[bold yellow]Would remove {len(all_orphans)} file(s).[/bold yellow]")
        return

    if not force:
        confirm = typer.confirm("Remove these orphan desktop files?")
        if not confirm:
            print("[dim]Cancelled.[/dim]")
            return

    # Remove orphan files and update metadata
    removed = backup.remove_orphan_files(all_orphans)

    print(f"\n[bold green]✨ Removed {removed} orphan desktop file(s).[/bold green]")
