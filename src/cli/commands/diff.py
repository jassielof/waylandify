import difflib
from pathlib import Path
from typing import Annotated

import typer
from rich import print

from cli import config, desktop
from cli.utils import _create_indexer, _load_config_or_exit

app = typer.Typer()


def _iter_target_files_for_program(program_settings, indexer, user_desktop_dir: Path):
    related_files = indexer.get_desktop_files_for_executables(
        program_settings.executables
    )
    if not related_files:
        return
    processed_targets: set[Path] = set()
    for source_path in related_files:
        target_path = user_desktop_dir / source_path.name
        if target_path in processed_targets:
            continue
        processed_targets.add(target_path)
        yield source_path, target_path


def _print_diff_header(source_path: Path, program_name: str):
    print(f"\n[bold cyan]{'─' * 60}[/bold cyan]")
    print(f"[bold]File:[/bold] {source_path.name}")
    print(f"[bold]Program:[/bold] {program_name}")
    print(f"[bold cyan]{'─' * 60}[/bold cyan]")


def _print_unified_diff(original: str, modified: str, source_name: str):
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{source_name}",
            tofile=f"b/{source_name}",
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


def _process_program_diff(program_settings, indexer, user_desktop_dir: Path) -> bool:
    any_changes = False
    for source_path, target_path in _iter_target_files_for_program(
        program_settings, indexer, user_desktop_dir
    ):
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
                _print_diff_header(source_path, program_settings.name)
                _print_unified_diff(
                    original_content, modified_content, source_path.name
                )
        except (FileNotFoundError, ValueError) as e:
            print(f"[yellow]⚠️  Could not process {source_path.name}: {e}[/yellow]")
    return any_changes


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
        any_changes |= _process_program_diff(
            program_settings, indexer, user_desktop_dir
        )

    if not any_changes:
        print("[dim]No changes would be made. All flags are already present.[/dim]")
