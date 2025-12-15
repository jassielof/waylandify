from pathlib import Path

import typer
from rich import print

from cli import backup, config
from cli.utils import _create_indexer

app = typer.Typer()


def _print_config_status():
    print("[bold cyan]Configuration:[/bold cyan]")
    if config.CONFIG_FILE_PATH.exists():
        print(f"  ✅ Config file: {config.CONFIG_FILE_PATH}")
        try:
            cfg = config.load_config()
            enabled_count = sum(1 for p in cfg.programs if p.enabled)
            print(f"  📋 Programs: {len(cfg.programs)} ({enabled_count} enabled)")
        except Exception as e:
            print(f"  ⚠️  Config error: {e}")
    else:
        print(f"  ❌ Config not found: {config.CONFIG_FILE_PATH}")
        print("     Run [cyan]waylandify init[/cyan] to create one.")


def _print_modified_files():
    print("\n[bold cyan]Modified Desktop Files:[/bold cyan]")
    modified_files = backup.get_modified_files()

    if modified_files:
        for mod in modified_files:
            target = Path(mod["target_path"])
            print(f"  • {target.name}")
            print(f"    [dim]Program: {mod.get('program_name', 'Unknown')}[/dim]")
        print(f"\n  [dim]Total: {len(modified_files)} file(s)[/dim]")
    else:
        print("  [dim]No modified desktop files tracked.[/dim]")


def _print_backups():
    print("\n[bold cyan]Backups:[/bold cyan]")
    stats = backup.get_backup_stats()
    if stats["total_backups"] > 0:
        print(f"  📦 {stats['total_dirs']} backup(s) available")
        print(f"  📁 Location: {backup.BACKUP_DIR}")
    else:
        print("  [dim]No backups found.[/dim]")


def _get_system_desktop_file_names(indexer, user_desktop_dir: Path) -> set[str]:
    names: set[str] = set()
    for directory in indexer.desktop_file_dirs:
        if directory == user_desktop_dir:
            continue
        if directory.is_dir():
            for desktop_file in directory.glob("*.desktop"):
                names.add(desktop_file.name)
    return names


def _collect_untracked_orphans(
    user_desktop_dir: Path, system_desktop_files: set[str], tracked_names: set[str]
) -> list[dict]:
    untracked: list[dict] = []
    if not user_desktop_dir.exists():
        return untracked
    for desktop_file in user_desktop_dir.glob("*.desktop"):
        if desktop_file.name in tracked_names:
            continue
        if desktop_file.name in system_desktop_files:
            continue
        if not backup._check_executable_exists(desktop_file):
            untracked.append(
                {"target_path": str(desktop_file), "program_name": "Untracked"}
            )
    return untracked


@app.command()
def status():
    """
    Show current status of waylandify modifications.

    Displays information about modified desktop files, available
    backups, and configuration status.

    Example:
        $ waylandify status
    """
    print("[bold]Waylandify Status[/bold]\n")

    _print_config_status()
    _print_modified_files()
    _print_backups()

    # Orphan files check
    print("\n[bold cyan]Orphan Files:[/bold cyan]")
    indexer = _create_indexer()
    user_desktop_dir = config.get_user_desktop_dir()
    system_desktop_files = _get_system_desktop_file_names(indexer, user_desktop_dir)

    # Find tracked orphans
    orphans = backup.find_orphan_desktop_files(system_desktop_files)

    # Also find untracked orphans
    tracked_files = {Path(o["target_path"]).name for o in orphans}
    tracked_files.update(
        Path(m["target_path"]).name for m in backup.get_modified_files()
    )
    untracked_orphans = _collect_untracked_orphans(
        user_desktop_dir, system_desktop_files, tracked_files
    )

    all_orphans = orphans + untracked_orphans

    if all_orphans:
        print(f"  [yellow]⚠️  {len(all_orphans)} orphan file(s) detected[/yellow]")
        for orphan in all_orphans:
            target = Path(orphan["target_path"])
            print(f"    • {target.name} ({orphan.get('program_name', 'Unknown')})")
        print("\n  [dim]Run [cyan]waylandify prune[/cyan] to remove orphans.[/dim]")
    else:
        print("  [dim]No orphan files found.[/dim]")
