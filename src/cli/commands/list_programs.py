from rich import print
from rich.table import Table
from typer import Typer

from cli import exec_parser
from cli.cli import _create_indexer, _load_config_or_exit

app = Typer()


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
