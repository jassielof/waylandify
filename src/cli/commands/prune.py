from pathlib import Path
from typing import Annotated

import typer
from rich import print

from cli import backup, config
from cli.utils import _create_indexer

app = typer.Typer()


def _get_system_desktop_file_names(indexer, user_desktop_dir: Path) -> set[str]:
    names: set[str] = set()
    for directory in indexer.desktop_file_dirs:
        if directory == user_desktop_dir:
            continue
        if directory.is_dir():
            for desktop_file in directory.glob("*.desktop"):
                names.add(desktop_file.name)
    return names


def _collect_orphans(
    user_desktop_dir: Path,
    system_desktop_files: set[str],
    tracked_modifications: dict[str, dict],
) -> list[dict]:
    all_orphans: list[dict] = []
    if not user_desktop_dir.exists():
        return all_orphans
    for desktop_file in user_desktop_dir.glob("*.desktop"):
        if desktop_file.name in system_desktop_files:
            continue
        if not backup._check_executable_exists(desktop_file):
            if desktop_file.name in tracked_modifications:
                mod_info = tracked_modifications[desktop_file.name]
                all_orphans.append(
                    {
                        "target_path": str(desktop_file),
                        "source_path": mod_info.get("source_path", str(desktop_file)),
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
    return all_orphans


def _print_orphans(orphans: list[dict]):
    print(f"[bold yellow]Found {len(orphans)} orphan desktop file(s):[/bold yellow]\n")
    for orphan in orphans:
        target_path = Path(orphan["target_path"])
        print(f"  🗑️  [cyan]{target_path.name}[/cyan]")
        print(f"      [dim]Program: {orphan.get('program_name', 'Unknown')}[/dim]")
        print(f"      [dim]Reason: {orphan.get('reason', 'Source not found')}[/dim]")
    print()


def _confirm_and_remove(*, dry_run: bool, force: bool, orphans: list[dict]):
    if dry_run:
        print(f"[bold yellow]Would remove {len(orphans)} file(s).[/bold yellow]")
        return
    if not force:
        if not typer.confirm("Remove these orphan desktop files?"):
            print("[dim]Cancelled.[/dim]")
            return
    removed = backup.remove_orphan_files(orphans)
    print(f"\n[bold green]✨ Removed {removed} orphan desktop file(s).[/bold green]")


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

    system_desktop_files = _get_system_desktop_file_names(indexer, user_desktop_dir)
    tracked_modifications = {
        Path(m["target_path"]).name: m for m in backup.get_modified_files()
    }
    all_orphans = _collect_orphans(
        user_desktop_dir, system_desktop_files, tracked_modifications
    )

    if not all_orphans:
        print("[bold green]✨ No orphan desktop files found.[/bold green]")
        return

    _print_orphans(all_orphans)
    _confirm_and_remove(dry_run=dry_run, force=force, orphans=all_orphans)
