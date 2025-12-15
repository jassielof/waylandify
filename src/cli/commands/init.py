from typer import Typer

from cli import config

app = Typer()


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
