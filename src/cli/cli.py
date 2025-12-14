"""
Command-line interface for waylandify.

This module provides the CLI commands for managing Wayland flags
in desktop files for Chromium-based applications.
"""

import difflib
import shutil
from importlib.metadata import version
from pathlib import Path

import typer
from rich import print
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from typing_extensions import Annotated

from . import backup, config, desktop, discovery, exec_parser

console = Console()

app = typer.Typer(
    help="A CLI tool to apply Wayland flags to Chromium-based applications.",
    no_args_is_help=True,
)


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

    Automatically modifies .desktop files to enable Wayland support
    without touching system files.
    """
    app()


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


@app.command()
def init():
    """
    Create a default configuration file.

    Creates a configuration file at ~/.config/waylandify/config.toml
    (or $XDG_CONFIG_HOME/waylandify/config.toml if set).

    Example:
        $ waylandify init
    """
    config.create_default_config()


@app.command()
def apply(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be changed without applying anything.",
        ),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            "-i",
            help="Confirm each change before applying.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed output for each file.",
        ),
    ] = False,
    prune: Annotated[
        bool,
        typer.Option(
            "--prune",
            "-p",
            help="Also remove orphan desktop files from uninstalled applications.",
        ),
    ] = False,
):
    """
    Apply Wayland flags to applications defined in the config file.

    Reads the configuration and modifies .desktop files for each
    program entry, adding the specified command-line flags.

    Examples:
        $ waylandify apply --dry-run     # Preview changes
        $ waylandify apply               # Apply changes
        $ waylandify apply --interactive # Confirm each change
        $ waylandify apply --verbose     # Show detailed output
        $ waylandify apply --prune       # Apply and remove orphan files
    """
    if dry_run:
        print("[bold yellow]Dry-run mode: No files will be changed.[/bold yellow]\n")

    if interactive:
        print(
            "[bold cyan]Interactive mode: You will be prompted for each change.[/bold cyan]\n"
        )

    cfg = _load_config_or_exit()
    user_desktop_dir = config.get_user_desktop_dir()

    if not user_desktop_dir.exists() and not dry_run:
        user_desktop_dir.mkdir(parents=True, exist_ok=True)

    indexer = _create_indexer()

    # Statistics
    stats = {
        "programs_processed": 0,
        "files_modified": 0,
        "files_skipped": 0,
        "files_already_ok": 0,
        "errors": 0,
    }

    # Track all configured target paths for stale detection
    all_configured_targets: set[Path] = set()

    for program_settings in cfg.programs:
        if not program_settings.enabled:
            if verbose:
                print(f"[dim]⏭️  Skipping '{program_settings.name}' (disabled)[/dim]")
            continue

        stats["programs_processed"] += 1
        related_files = indexer.get_desktop_files_for_executables(
            program_settings.executables
        )

        if not related_files:
            if verbose:
                print(
                    f"[yellow]⚠️  No desktop files found for '{program_settings.name}'[/yellow]"
                )
            continue

        # Get merged flags for display
        merged_flags = exec_parser.format_flags_display(
            program_settings.flags,
            merge_enable_features=program_settings.merge_enable_features,
        )

        if verbose:
            print(f"\n[bold magenta]{program_settings.name}[/bold magenta]")
            print(f"  [dim]Flags: {merged_flags}[/dim]")
            print(f"  [dim]Found {len(related_files)} desktop file(s)[/dim]")

        # Deduplicate by target filename
        processed_targets: set[Path] = set()

        for source_path in related_files:
            target_path = user_desktop_dir / source_path.name

            if target_path in processed_targets:
                continue

            # Track all configured targets for stale detection
            all_configured_targets.add(target_path)

            # Get previously applied flags for this file
            previous_flags = backup.get_previous_flags(target_path)

            try:
                # Use sync to both remove old flags and add new ones
                modified_content, was_modified = desktop.sync_flags_to_desktop_file(
                    user_path=target_path,
                    system_path=source_path,
                    desired_flags=program_settings.flags,
                    previous_flags=previous_flags,
                    merge_enable_features=program_settings.merge_enable_features,
                )
            except (FileNotFoundError, ValueError) as e:
                stats["errors"] += 1
                print(f"[bold red]❌ Error parsing {source_path.name}: {e}[/bold red]")
                continue

            processed_targets.add(target_path)

            if not was_modified:
                stats["files_already_ok"] += 1
                if verbose:
                    print(f"  [dim]✓ {source_path.name} (already OK)[/dim]")
                continue

            # Interactive confirmation
            if interactive and not dry_run:
                print(f"\n  [cyan]{source_path.name}[/cyan]")
                print(f"    Flags: {merged_flags}")
                confirm = typer.confirm("    Apply changes?")
                if not confirm:
                    stats["files_skipped"] += 1
                    print("    [yellow]Skipped[/yellow]")
                    continue

            if dry_run:
                stats["files_modified"] += 1
                print(f"  [yellow]→ {source_path.name}[/yellow] (would modify)")
            else:
                try:
                    # Create backup if target exists
                    if target_path.exists():
                        backup.create_backup(target_path)
                    elif source_path != target_path:
                        shutil.copy2(source_path, target_path)

                    target_path.write_text(modified_content)

                    # Record the modification
                    backup.record_modification(
                        target_path=target_path,
                        source_path=source_path,
                        program_name=program_settings.name,
                        flags_applied=program_settings.flags,
                    )

                    stats["files_modified"] += 1
                    print(f"  [green]✓ {source_path.name}[/green]")

                except Exception as e:
                    stats["errors"] += 1
                    print(f"  [bold red]❌ {source_path.name}: {e}[/bold red]")

    # Find and handle stale modifications (programs removed from config)
    stale = backup.find_stale_modifications(all_configured_targets)

    # Also find untracked user files that differ from system (modified before tracking)
    untracked = backup.find_untracked_user_files(
        all_configured_targets,
        user_desktop_dir,
        list(indexer.desktop_file_dirs),
    )

    # Combine both lists
    all_stale = stale + untracked

    if all_stale:
        print()
        print(
            f"[bold yellow]Found {len(all_stale)} stale desktop file(s) (no longer in config):[/bold yellow]"
        )
        for mod in all_stale:
            target_path = Path(mod["target_path"])
            print(
                f"  🗑️  [cyan]{target_path.name}[/cyan] ({mod.get('program_name', 'Unknown')})"
            )

        if dry_run:
            print(
                f"\n[bold yellow]Would remove {len(all_stale)} stale file(s).[/bold yellow]"
            )
        else:
            removed = backup.remove_stale_modifications(all_stale)
            print(
                f"\n[bold green]✨ Removed {removed} stale desktop file(s).[/bold green]"
            )

    # Summary
    print()
    if stats["files_modified"] == 0 and stats["files_already_ok"] > 0:
        print(
            f"[bold green]✨ All {stats['files_already_ok']} file(s) already have the correct flags.[/bold green]"
        )
    elif dry_run:
        print(
            f"[bold yellow]Would modify {stats['files_modified']} file(s).[/bold yellow]"
        )
        if stats["files_already_ok"] > 0:
            print(f"[dim]{stats['files_already_ok']} file(s) already OK.[/dim]")
    else:
        print(
            f"[bold green]✨ Modified {stats['files_modified']} file(s).[/bold green]"
        )
        if stats["files_already_ok"] > 0:
            print(
                f"[dim]{stats['files_already_ok']} file(s) already had correct flags.[/dim]"
            )
        if stats["files_skipped"] > 0:
            print(f"[dim]{stats['files_skipped']} file(s) skipped by user.[/dim]")
        if stats["errors"] > 0:
            print(f"[yellow]{stats['errors']} error(s) occurred.[/yellow]")

    # Prune orphan desktop files if requested
    if prune:
        print()
        # Get all system desktop file names (excluding user directory)
        system_desktop_files: set[str] = set()
        for directory in indexer.desktop_file_dirs:
            # Exclude user directory - we're looking for system-installed files
            if directory == user_desktop_dir:
                continue
            if directory.is_dir():
                for desktop_file in directory.glob("*.desktop"):
                    system_desktop_files.add(desktop_file.name)

        orphans = backup.find_orphan_desktop_files(system_desktop_files)

        if orphans:
            print(
                f"[bold yellow]Found {len(orphans)} orphan desktop file(s):[/bold yellow]"
            )
            for orphan in orphans:
                target_path = Path(orphan["target_path"])
                print(
                    f"  🗑️  [cyan]{target_path.name}[/cyan] ({orphan.get('program_name', 'Unknown')})"
                )

            if dry_run:
                print(
                    f"\n[bold yellow]Would remove {len(orphans)} orphan file(s).[/bold yellow]"
                )
            else:
                removed = backup.remove_orphan_files(orphans)
                print(
                    f"\n[bold green]✨ Removed {removed} orphan desktop file(s).[/bold green]"
                )
        else:
            print("[dim]No orphan desktop files found.[/dim]")


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


@app.command(name="list")
def list_programs():
    """
    List all programs and their associated desktop files.

    Shows which programs from your configuration have matching
    .desktop files on your system.

    Example:
        $ waylandify list
    """
    cfg = _load_config_or_exit()
    indexer = _create_indexer()

    table = Table(
        title="Configured Programs", show_header=True, header_style="bold magenta"
    )
    table.add_column("Program", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Flags", style="dim")
    table.add_column("Files", justify="right", style="yellow")

    for program in cfg.programs:
        related_files = indexer.get_desktop_files_for_executables(program.executables)
        status = "✅ Found" if related_files else "⚠️  Not found"
        if not program.enabled:
            status = "⏸️  Disabled"

        # Show merged flags
        merged_flags = exec_parser.format_flags_display(
            program.flags, merge_enable_features=program.merge_enable_features
        )
        # Truncate for display
        if len(merged_flags) > 40:
            merged_flags = merged_flags[:37] + "..."

        table.add_row(
            program.name,
            status,
            merged_flags,
            str(len(related_files)),
        )

    print(table)

    # Show details
    print("\n[bold]Desktop File Details:[/bold]")
    for program in cfg.programs:
        if not program.enabled:
            continue
        related_files = indexer.get_desktop_files_for_executables(program.executables)
        if related_files:
            print(f"\n[cyan]{program.name}[/cyan]:")
            for f in related_files:
                print(f"  • {f}")


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

    # Config status
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

    # Modified files
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

    # Backup status
    print("\n[bold cyan]Backups:[/bold cyan]")
    stats = backup.get_backup_stats()
    if stats["total_backups"] > 0:
        print(f"  📦 {stats['total_dirs']} backup(s) available")
        print(f"  📁 Location: {backup.BACKUP_DIR}")
    else:
        print("  [dim]No backups found.[/dim]")

    # Orphan files check
    print("\n[bold cyan]Orphan Files:[/bold cyan]")
    indexer = _create_indexer()
    user_desktop_dir = config.get_user_desktop_dir()
    system_desktop_files: set[str] = set()
    for directory in indexer.desktop_file_dirs:
        # Exclude user directory - we're looking for system-installed files
        if directory == user_desktop_dir:
            continue
        if directory.is_dir():
            for desktop_file in directory.glob("*.desktop"):
                system_desktop_files.add(desktop_file.name)

    # Find tracked orphans
    orphans = backup.find_orphan_desktop_files(system_desktop_files)

    # Also find untracked orphans
    untracked_orphans: list[dict] = []
    if user_desktop_dir.exists():
        tracked_files = {Path(o["target_path"]).name for o in orphans}
        tracked_files.update(
            Path(m["target_path"]).name for m in backup.get_modified_files()
        )

        for desktop_file in user_desktop_dir.glob("*.desktop"):
            # Skip if already tracked
            if desktop_file.name in tracked_files:
                continue
            # Skip if the file exists in system directories (not an orphan)
            if desktop_file.name in system_desktop_files:
                continue
            # Check if the executable exists
            if not backup._check_executable_exists(desktop_file):
                untracked_orphans.append(
                    {
                        "target_path": str(desktop_file),
                        "program_name": "Untracked",
                    }
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


@app.command()
def diff(
    program_name: Annotated[
        str | None,
        typer.Argument(help="Show diff for a specific program only"),
    ] = None,
):
    """
    Show what changes would be made to desktop files.

    Displays a unified diff of the modifications that would be
    applied by the 'apply' command.

    Examples:
        $ waylandify diff                 # Show all diffs
        $ waylandify diff "Electron Apps" # Show diff for specific program
    """
    cfg = _load_config_or_exit()
    indexer = _create_indexer()
    user_desktop_dir = config.get_user_desktop_dir()

    any_changes = False

    for program_settings in cfg.programs:
        if program_name and program_settings.name != program_name:
            continue

        if not program_settings.enabled:
            continue

        related_files = indexer.get_desktop_files_for_executables(
            program_settings.executables
        )

        if not related_files:
            continue

        processed_targets: set[Path] = set()

        for source_path in related_files:
            target_path = user_desktop_dir / source_path.name

            if target_path in processed_targets:
                continue

            file_to_check = target_path if target_path.exists() else source_path

            try:
                original_content = file_to_check.read_text()
                modified_content, was_modified = desktop.apply_flags_to_desktop_file(
                    file_to_check,
                    program_settings.flags,
                    merge_enable_features=program_settings.merge_enable_features,
                )

                if was_modified:
                    any_changes = True
                    print(f"\n[bold cyan]{'─' * 60}[/bold cyan]")
                    print(f"[bold]File:[/bold] {source_path.name}")
                    print(f"[bold]Program:[/bold] {program_settings.name}")
                    print(f"[bold cyan]{'─' * 60}[/bold cyan]")

                    diff_lines = list(
                        difflib.unified_diff(
                            original_content.splitlines(keepends=True),
                            modified_content.splitlines(keepends=True),
                            fromfile=f"a/{source_path.name}",
                            tofile=f"b/{source_path.name}",
                            lineterm="",
                        )
                    )

                    for line in diff_lines:
                        line = line.rstrip("\n")
                        if line.startswith("+") and not line.startswith("+++"):
                            print(f"[green]{line}[/green]")
                        elif line.startswith("-") and not line.startswith("---"):
                            print(f"[red]{line}[/red]")
                        elif line.startswith("@@"):
                            print(f"[cyan]{line}[/cyan]")
                        else:
                            print(line)

                processed_targets.add(target_path)

            except (FileNotFoundError, ValueError) as e:
                print(f"[yellow]⚠️  Could not process {source_path.name}: {e}[/yellow]")

    if not any_changes:
        print("[dim]No changes would be made. All flags are already present.[/dim]")


@app.command()
def verify():
    """
    Verify that applied flags are still present in desktop files.

    Checks if the Wayland flags you configured are still present
    in the user desktop files. Useful after system updates that
    might overwrite your modifications.

    Example:
        $ waylandify verify
    """
    cfg = _load_config_or_exit()
    indexer = _create_indexer()
    user_desktop_dir = config.get_user_desktop_dir()

    print("[bold]Verifying applied flags...[/bold]\n")

    issues_found = 0
    files_checked = 0
    files_ok = 0

    for program_settings in cfg.programs:
        if not program_settings.enabled:
            continue

        related_files = indexer.get_desktop_files_for_executables(
            program_settings.executables
        )

        if not related_files:
            continue

        processed_targets: set[Path] = set()

        for source_path in related_files:
            target_path = user_desktop_dir / source_path.name

            if target_path in processed_targets:
                continue

            if not target_path.exists():
                continue

            files_checked += 1
            processed_targets.add(target_path)

            try:
                _, needs_modification = desktop.apply_flags_to_desktop_file(
                    target_path,
                    program_settings.flags,
                    merge_enable_features=program_settings.merge_enable_features,
                )

                if needs_modification:
                    issues_found += 1
                    print(f"[yellow]⚠️  {target_path.name}[/yellow]")
                    print(f"   [dim]Program: {program_settings.name}[/dim]")
                else:
                    files_ok += 1

            except (FileNotFoundError, ValueError) as e:
                issues_found += 1
                print(f"[red]❌ {target_path.name}: {e}[/red]")

    print("-" * 40)

    if files_checked == 0:
        print("[dim]No modified desktop files found to verify.[/dim]")
        print("Run [cyan]waylandify apply[/cyan] first.")
    elif issues_found == 0:
        print(
            f"[bold green]✅ All {files_ok} file(s) verified successfully![/bold green]"
        )
    else:
        print(
            f"[bold yellow]⚠️  {issues_found} file(s) have missing flags.[/bold yellow]"
        )
        print(f"[dim]{files_ok} file(s) are OK.[/dim]")
        print("\nRun [cyan]waylandify apply[/cyan] to re-apply flags.")
        raise typer.Exit(code=1)


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


@app.command()
def validate():
    """
    Validate the configuration file.

    Checks if the configuration file exists, is valid TOML,
    and conforms to the expected schema.

    Example:
        $ waylandify validate
    """
    print("[bold]Validating configuration...[/bold]\n")

    if not config.CONFIG_FILE_PATH.exists():
        print("[bold red]❌ Config file not found[/bold red]")
        print(f"   Expected: {config.CONFIG_FILE_PATH}")
        print("\n   Run [cyan]waylandify init[/cyan] to create one.")
        raise typer.Exit(code=1)

    print(f"[green]✅ Config file found:[/green] {config.CONFIG_FILE_PATH}")

    try:
        cfg = config.load_config()
    except FileNotFoundError:
        print("[bold red]❌ Could not read configuration file[/bold red]")
        raise typer.Exit(code=1)
    except Exception:
        print("[bold red]❌ Configuration validation failed[/bold red]")
        raise typer.Exit(code=1)

    print("[green]✅ TOML syntax valid[/green]")
    print("[green]✅ Schema validation passed[/green]")

    print("\n[bold]Programs:[/bold]")

    errors: list[str] = []
    warnings: list[str] = []

    for i, program in enumerate(cfg.programs):
        # Show merged flags
        merged_flags = exec_parser.format_flags_display(
            program.flags, merge_enable_features=program.merge_enable_features
        )

        status = "✅" if program.enabled else "⏸️"
        print(f"\n  {status} [{i + 1}] [cyan]{program.name}[/cyan]")
        print(f"      Executables: {', '.join(program.executables[:3])}")
        print(f"      Flags: {merged_flags}")

        if not program.executables:
            errors.append(f"'{program.name}' has no executables")

        if not program.flags:
            warnings.append(f"'{program.name}' has no flags")

        for flag in program.flags:
            if not flag.startswith("-"):
                warnings.append(
                    f"Flag '{flag}' in '{program.name}' doesn't start with '-'"
                )

    print("\n" + "-" * 40)

    if errors:
        print("\n[bold red]Errors:[/bold red]")
        for error in errors:
            print(f"  ❌ {error}")

    if warnings:
        print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in warnings:
            print(f"  ⚠️  {warning}")

    if errors:
        print("\n[bold red]❌ Fix the errors above.[/bold red]")
        raise typer.Exit(code=1)
    elif warnings:
        print("\n[bold yellow]⚠️  Valid with warnings.[/bold yellow]")
    else:
        print("\n[bold green]✅ Configuration is valid![/bold green]")


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
