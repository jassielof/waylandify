import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich import print
from typer import Typer
from xdg_desktop_entry.exec import format_flags as format_exec_flags

from cli import backup, config
from cli.desktop_entry_ops import sync_flags_in_file
from cli.utils import _create_indexer, _load_config_or_exit

app = Typer()


def _get_system_desktop_file_names(indexer, user_desktop_dir: Path) -> set[str]:
    names: set[str] = set()
    for directory in indexer.desktop_file_dirs:
        if directory == user_desktop_dir:
            continue
        if directory.is_dir():
            for desktop_file in directory.glob("*.desktop"):
                names.add(desktop_file.name)
    return names


def _process_single_file(
    source_path: Path,
    target_path: Path,
    program_settings,
    merged_flags: str,
    previous_flags: list[str] | None,
    *,
    dry_run: bool,
    interactive: bool,
    verbose: bool,
    stats: dict,
):
    try:
        input_path = target_path if target_path.exists() else source_path
        modified_content, was_modified = sync_flags_in_file(
            input_path,
            desired_flags=program_settings.flags,
            previous_flags=previous_flags,
            merge_enable_features=program_settings.merge_enable_features,
        )
    except (FileNotFoundError, ValueError) as e:
        stats["errors"] += 1
        print(f"[bold red]❌ Error parsing {source_path.name}: {e}[/bold red]")
        return

    if not was_modified:
        stats["files_already_ok"] += 1
        if verbose:
            print(f"  [dim]✓ {source_path.name} (already OK)[/dim]")
        return

    if interactive and not dry_run:
        print(f"\n  [cyan]{source_path.name}[/cyan]")
        print(f"    Flags: {merged_flags}")
        if not typer.confirm("    Apply changes?"):
            stats["files_skipped"] += 1
            print("    [yellow]Skipped[/yellow]")
            return

    if dry_run:
        stats["files_modified"] += 1
        print(f"  [yellow]→ {source_path.name}[/yellow] (would modify)")
        return

    try:
        if target_path.exists():
            backup.create_backup(target_path)
        elif source_path != target_path:
            shutil.copy2(source_path, target_path)

        target_path.write_text(modified_content)

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


def _process_program(
    program_settings,
    *,
    indexer,
    user_desktop_dir: Path,
    dry_run: bool,
    interactive: bool,
    verbose: bool,
    stats: dict,
    all_configured_targets: set[Path],
):
    related_files = indexer.get_desktop_files_for_executables(
        program_settings.executables
    )

    if not related_files:
        if verbose:
            print(
                f"[yellow]⚠️  No desktop files found for '{program_settings.name}'[/yellow]"
            )
        return

    merged_flags = format_exec_flags(
        program_settings.flags,
        merge_enable_features=program_settings.merge_enable_features,
    )

    if verbose:
        print(f"\n[bold magenta]{program_settings.name}[/bold magenta]")
        print(f"  [dim]Flags: {merged_flags}[/dim]")
        print(f"  [dim]Found {len(related_files)} desktop file(s)[/dim]")

    processed_targets: set[Path] = set()

    for source_path in related_files:
        target_path = user_desktop_dir / source_path.name
        if target_path in processed_targets:
            continue

        all_configured_targets.add(target_path)
        previous_flags = backup.get_previous_flags(target_path)
        _process_single_file(
            source_path,
            target_path,
            program_settings,
            merged_flags,
            previous_flags,
            dry_run=dry_run,
            interactive=interactive,
            verbose=verbose,
            stats=stats,
        )
        processed_targets.add(target_path)


def _handle_stale_and_untracked(
    *,
    all_configured_targets: set[Path],
    user_desktop_dir: Path,
    indexer,
    dry_run: bool,
):
    stale = backup.find_stale_modifications(all_configured_targets)
    untracked = backup.find_untracked_user_files(
        all_configured_targets,
        user_desktop_dir,
        list(indexer.desktop_file_dirs),
    )
    all_stale = stale + untracked

    if not all_stale:
        return

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
        return

    removed = backup.remove_stale_modifications(all_stale)
    print(f"\n[bold green]✨ Removed {removed} stale desktop file(s).[/bold green]")


def _print_summary(stats: dict, *, dry_run: bool):
    print()
    if stats["files_modified"] == 0 and stats["files_already_ok"] > 0:
        print(
            f"[bold green]✨ All {stats['files_already_ok']} file(s) already have the correct flags.[/bold green]"
        )
        return
    if dry_run:
        print(
            f"[bold yellow]Would modify {stats['files_modified']} file(s).[/bold yellow]"
        )
        if stats["files_already_ok"] > 0:
            print(f"[dim]{stats['files_already_ok']} file(s) already OK.[/dim]")
        return
    print(f"[bold green]✨ Modified {stats['files_modified']} file(s).[/bold green]")
    if stats["files_already_ok"] > 0:
        print(
            f"[dim]{stats['files_already_ok']} file(s) already had correct flags.[/dim]"
        )
    if stats["files_skipped"] > 0:
        print(f"[dim]{stats['files_skipped']} file(s) skipped by user.[/dim]")
    if stats["errors"] > 0:
        print(f"[yellow]{stats['errors']} error(s) occurred.[/yellow]")


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
        _process_program(
            program_settings,
            indexer=indexer,
            user_desktop_dir=user_desktop_dir,
            dry_run=dry_run,
            interactive=interactive,
            verbose=verbose,
            stats=stats,
            all_configured_targets=all_configured_targets,
        )

    _handle_stale_and_untracked(
        all_configured_targets=all_configured_targets,
        user_desktop_dir=user_desktop_dir,
        indexer=indexer,
        dry_run=dry_run,
    )

    _print_summary(stats, dry_run=dry_run)

    # Prune orphan desktop files if requested
    if prune:
        print()
        system_desktop_files = _get_system_desktop_file_names(indexer, user_desktop_dir)
        orphans = backup.find_orphan_desktop_files(system_desktop_files)

        if not orphans:
            print("[dim]No orphan desktop files found.[/dim]")
            return

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
            return
        removed = backup.remove_orphan_files(orphans)
        print(
            f"\n[bold green]✨ Removed {removed} orphan desktop file(s).[/bold green]"
        )
