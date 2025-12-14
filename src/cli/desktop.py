"""
Desktop file manipulation utilities.

This module provides functions for parsing and modifying .desktop files,
particularly for adding command-line flags to Exec entries.
"""

import configparser
import io
from pathlib import Path

from . import exec_parser


def add_flags_to_exec_command(
    exec_cmd: str, flags: list[str], merge_enable_features: bool = True
) -> tuple[str, bool]:
    """
    Intelligently adds flags to an Exec command string, avoiding duplicates.

    Uses the exec_parser module to properly parse Desktop Entry Exec format
    and handle various flag formats (--flag value, --flag=value, -f, %F, etc.)

    Args:
        exec_cmd: The original Exec command string
        flags: List of flags to add to the command
        merge_enable_features: If True, merge --enable-features values instead
            of adding duplicate flags (Chromium-style)

    Returns:
        A tuple of (modified_command, was_modified) where was_modified indicates
        if any changes were made

    Examples:
        >>> add_flags_to_exec_command("/usr/bin/code", ["--ozone-platform=wayland"])
        ('/usr/bin/code --ozone-platform=wayland', True)

        >>> add_flags_to_exec_command("/usr/bin/code --ozone-platform=wayland", ["--ozone-platform=wayland"])
        ('/usr/bin/code --ozone-platform=wayland', False)
    """
    return exec_parser.add_flags_to_exec(
        exec_cmd, flags, merge_enable_features=merge_enable_features
    )


def apply_flags_to_desktop_file(
    path: Path, flags: list[str], merge_enable_features: bool = True
) -> tuple[str, bool]:
    """
    Parses a .desktop file, applies flags to all Exec keys, and returns the new content.

    Args:
        path: Path to the .desktop file to modify
        flags: List of command-line flags to add
        merge_enable_features: If True, merge --enable-features values instead
            of adding duplicate flags (Chromium-style)

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
            modified_exec, was_modified = add_flags_to_exec_command(
                original_exec, flags, merge_enable_features=merge_enable_features
            )
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


def sync_flags_to_desktop_file(
    user_path: Path,
    system_path: Path,
    desired_flags: list[str],
    previous_flags: list[str],  # Kept for API compatibility but not used
    merge_enable_features: bool = True,
) -> tuple[str, bool]:
    """
    Synchronize flags in a desktop file using the system file as baseline.

    This function:
    1. ALWAYS reads the system desktop file (original, unmodified baseline)
    2. Applies desired flags to the baseline
    3. Compares with current user file (if exists)
    4. Returns (new_content, was_modified)

    This ensures flag sync works correctly regardless of metadata state.

    Args:
        user_path: Path to the user's modified desktop file
        system_path: Path to the original system desktop file
        desired_flags: List of flags that should be present
        previous_flags: Unused, kept for API compatibility
        merge_enable_features: If True, merge --enable-features values

    Returns:
        A tuple of (modified_content, was_modified)

    Raises:
        FileNotFoundError: If system file doesn't exist
        ValueError: If the desktop file cannot be parsed
    """
    # ALWAYS read from system file as baseline
    if not system_path.exists():
        # Fall back to user file if system doesn't exist (e.g., user-created entries)
        if user_path.exists():
            source_path = user_path
        else:
            raise FileNotFoundError(f"Neither {user_path} nor {system_path} found")
    else:
        source_path = system_path

    # Read and apply flags to the baseline (system file)
    new_content, _ = apply_flags_to_desktop_file(
        source_path, desired_flags, merge_enable_features=merge_enable_features
    )

    # Compare with current user file content
    if user_path.exists():
        try:
            current_content = user_path.read_text().strip()
            # Normalize both for comparison (strip whitespace)
            was_modified = new_content.strip() != current_content
        except (IOError, UnicodeDecodeError):
            was_modified = True
    else:
        # User file doesn't exist, so we need to create it
        was_modified = True

    return new_content, was_modified
