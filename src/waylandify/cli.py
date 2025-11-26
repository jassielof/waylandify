import shutil
from pathlib import Path
from typing_extensions import Annotated

import typer
from rich import print

from . import config, discovery, desktop, backup

app = typer.Typer(
    help="A CLI tool to apply Wayland flags to Chromium-based applications."
)


@app.command()
def init():
    """
    Creates a default configuration file at ~/.config/waylandify/config.toml
    """
    config.create_default_config()


@app.command()
def apply(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show what would be changed without applying anything."
        ),
    ] = False,
):
    """
    Applies Wayland flags to the applications defined in the config file.
    """

    if dry_run:
        print(
            "[bold yellow]Running in dry-run mode. No files will be changed.[/bold yellow]"
        )

    try:
        cfg = config.load_config()
    except Exception:
        raise typer.Exit(code=1)

    all_desktop_files = discovery.get_all_desktop_files()
    user_desktop_dir = Path.home() / ".local/share/applications"

    if not user_desktop_dir.exists() and not dry_run:
        user_desktop_dir.mkdir(parents=True, exist_ok=True)

    print("-" * 30)

    # --- MODIFIED LOOP HERE ---
    for program_settings in cfg.programs:
        print(f"[bold magenta]Processing '{program_settings.name}'...[/bold magenta]")

        exec_path = discovery.find_executable_path(program_settings.executables)
        if not exec_path:
            print(
                f"  [yellow]⚠️  Could not find executable for any of: {program_settings.executables}. Skipping.[/yellow]"
            )
            continue

        print(f"  [dim]Found executable: {exec_path}[/dim]")

        # We need to pass ProgramSettings to discovery now
        related_files = discovery.find_related_desktop_files(
            exec_path, program_settings.executables, all_desktop_files
        )

        if not related_files:
            print("  [yellow]No related .desktop files found.[/yellow]")
            continue

        # Deduplicate: group by target filename to avoid processing the same target multiple times
        processed_targets = set()

        for source_path in related_files:
            target_path = user_desktop_dir / source_path.name

            # Skip if we've already processed this target file in this iteration
            if target_path in processed_targets:
                continue

            # If target exists and is already in user dir, check it for modifications
            # If it's in system dir and target exists, skip (prefer existing user file)
            file_to_check = target_path if target_path.exists() else source_path

            print(f"  -> Found desktop file: [cyan]{source_path}[/cyan]")

            try:
                modified_content, was_modified = desktop.apply_flags_to_desktop_file(
                    file_to_check, program_settings.flags
                )
            except (FileNotFoundError, ValueError) as e:
                print(f"     [bold red]❌ Error parsing desktop file: {e}[/bold red]")
                continue

            print(f"     [bold]Target path:[/bold] {target_path}")
            print(f"     [bold]Flags to add:[/bold] {' '.join(program_settings.flags)}")

            if not was_modified:
                print("     [dim]⏭️  No changes needed (flags already present)[/dim]")
                processed_targets.add(target_path)
                continue

            if not dry_run:
                try:
                    if target_path.exists():
                        backup.create_backup(target_path)
                    elif source_path != target_path:
                        # Only copy metadata if creating new file
                        shutil.copy2(source_path, target_path)

                    target_path.write_text(modified_content)
                    print("     [green]✅ Applied flags successfully.[/green]")
                    processed_targets.add(target_path)

                except Exception as e:
                    print(f"     [bold red]❌ Error applying flags: {e}[/bold red]")
                    raise typer.Exit(code=1)
            else:
                print("     [yellow]Would apply changes (dry-run mode)[/yellow]")
                processed_targets.add(target_path)
        print("-" * 30)

    if not dry_run:
        print("\n[bold green]✨ All operations completed successfully! ✨[/bold green]")


@app.command()
def restore(
    backup_id: Annotated[
        str | None,
        typer.Argument(help="Backup directory name to restore from (e.g., backup_20240101_120000_123456)"),
    ] = None,
    remove_only: Annotated[
        bool,
        typer.Option(
            "--remove-only",
            help="Remove modified desktop files without restoring backups (reverts to system defaults)",
        ),
    ] = False,
):
    """
    Restore desktop files from a backup or revert to system defaults.

    Without arguments, lists available backups.
    With --remove-only, removes user desktop files to use system defaults.
    With a backup ID, restores files from that specific backup.
    """
    from rich.table import Table

    if remove_only:
        print("[bold yellow]Removing modified desktop files...[/bold yellow]")
        count = backup.remove_user_desktop_files()
        if count > 0:
            print(f"\n[bold green]✨ Removed {count} file(s). System will now use default desktop files.[/bold green]")
        else:
            print("[dim]No modified desktop files found.[/dim]")
        return

    if backup_id is None:
        # List available backups
        backups = backup.list_backups()

        if not backups:
            print("[dim]No backups found.[/dim]")
            print("\nTo create backups, run: [cyan]waylandify apply[/cyan]")
            return

        # Group backups by backup_dir for cleaner display
        backup_dirs = {}
        for b in backups:
            dir_name = Path(b["backup_dir"]).name
            if dir_name not in backup_dirs:
                backup_dirs[dir_name] = []
            backup_dirs[dir_name].append(b)

        table = Table(title="Available Backups", show_header=True, header_style="bold magenta")
        table.add_column("Backup ID", style="cyan")
        table.add_column("Date/Time", style="green")
        table.add_column("Files", justify="right", style="yellow")

        for dir_name, backup_list in sorted(backup_dirs.items(), reverse=True):
            # Parse timestamp from directory name
            try:
                timestamp_str = dir_name.replace("backup_", "")
                # Format: YYYYMMDD_HHMMSS_microseconds
                date_part = timestamp_str[:8]
                time_part = timestamp_str[9:15]
                formatted = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            except Exception:
                formatted = timestamp_str

            table.add_row(dir_name, formatted, str(len(backup_list)))

        print(table)
        print("\nTo restore a backup, run: [cyan]waylandify restore <backup_id>[/cyan]")
        print("To remove modified files (use system defaults): [cyan]waylandify restore --remove-only[/cyan]")
        return

    # Restore from specific backup
    backup_dir_path = backup.BACKUP_DIR / backup_id

    print(f"[bold yellow]Restoring from backup: {backup_id}[/bold yellow]")
    success = backup.restore_from_backup(backup_dir_path)

    if success:
        print("\n[bold green]✨ Restore completed successfully![/bold green]")
    else:
        print("\n[bold red]❌ Restore completed with errors.[/bold red]")
        raise typer.Exit(code=1)
