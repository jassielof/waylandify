"""
Desktop file manipulation utilities.

This module provides functions for parsing and modifying .desktop files,
particularly for adding command-line flags to Exec entries.
"""

import configparser
import io
from pathlib import Path

from . import exec_parser


def add_flags_to_exec_command(exec_cmd: str, flags: list[str]) -> tuple[str, bool]:
    """
    Intelligently adds flags to an Exec command string, avoiding duplicates.

    Uses the exec_parser module to properly parse Desktop Entry Exec format
    and handle various flag formats (--flag value, --flag=value, -f, %F, etc.)

    Args:
        exec_cmd: The original Exec command string
        flags: List of flags to add to the command

    Returns:
        A tuple of (modified_command, was_modified) where was_modified indicates
        if any changes were made

    Examples:
        >>> add_flags_to_exec_command("/usr/bin/code", ["--ozone-platform=wayland"])
        ('/usr/bin/code --ozone-platform=wayland', True)

        >>> add_flags_to_exec_command("/usr/bin/code --ozone-platform=wayland", ["--ozone-platform=wayland"])
        ('/usr/bin/code --ozone-platform=wayland', False)
    """
    return exec_parser.add_flags_to_exec(exec_cmd, flags)


def apply_flags_to_desktop_file(path: Path, flags: list[str]) -> tuple[str, bool]:
    """
    Parses a .desktop file, applies flags to all Exec keys, and returns the new content.

    Args:
        path: Path to the .desktop file to modify
        flags: List of command-line flags to add

    Returns:
        A tuple of (modified_content, was_modified) where was_modified indicates
        if any Exec entries were changed

    Raises:
        FileNotFoundError: If the desktop file doesn't exist
        ValueError: If the desktop file cannot be parsed
    """
    if not path.exists():
        raise FileNotFoundError(f"Desktop file not found: {path}")

    parser = configparser.ConfigParser(
        delimiters=("=",),
        interpolation=None,
        allow_no_value=True,  # Makes parsing more robust for .desktop files
    )
    # Preserve the case of keys
    parser.optionxform = str

    try:
        content = path.read_text()
    except (IOError, UnicodeDecodeError) as e:
        raise ValueError(f"Cannot read desktop file {path}: {e}")

    # Some .desktop files (especially PWAs) start with a shebang.
    # configparser sees this as an error. We must filter it out before parsing.
    shebang = None
    if content.startswith("#!"):
        lines = content.splitlines()
        shebang = lines[0]
        content = "\n".join(lines[1:])

    try:
        parser.read_string(content)
    except configparser.Error as e:
        raise ValueError(f"Cannot parse desktop file {path}: {e}")

    # Apply flags to all 'Exec' entries in every section
    any_modified = False
    for section in parser.sections():
        if parser.has_option(section, "Exec"):
            original_exec = parser.get(section, "Exec")
            modified_exec, was_modified = add_flags_to_exec_command(original_exec, flags)
            if was_modified:
                parser.set(section, "Exec", modified_exec)
                any_modified = True

    # Write the modified configuration to a string
    string_io = io.StringIO()
    parser.write(string_io, space_around_delimiters=False)
    result = string_io.getvalue().strip()

    # Restore shebang if it existed
    if shebang:
        result = f"{shebang}\n{result}"

    return result, any_modified
