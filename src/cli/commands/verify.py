from pathlib import Path

import typer
from rich import print

from cli import config, desktop
from cli.utils import _create_indexer, _load_config_or_exit

app = typer.Typer()


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
