import typer
from rich import print

from cli import config, exec_parser
app = typer.Typer()

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
