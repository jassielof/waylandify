"""
Desktop file discovery and executable path resolution.

This module provides utilities for finding executables in the system PATH
and locating related .desktop files that reference those executables.
"""

import shutil
from pathlib import Path


# Standard directories where .desktop files are stored
DESKTOP_FILE_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
]


def find_executable_path(names: list[str]) -> str | None:
    """
    Find the full path of an executable from a list of possible names.

    Args:
        names: List of executable names to search for (e.g., ["code", "code-insiders"])

    Returns:
        Full path to the first executable found, or None if none are found
    """
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def get_all_desktop_files() -> list[Path]:
    """
    Scan standard directories and return a list of all .desktop files.

    Searches in:
    - /usr/share/applications
    - /usr/local/share/applications
    - ~/.local/share/applications

    Returns:
        List of paths to .desktop files found
    """
    all_files = []
    for directory in DESKTOP_FILE_DIRS:
        if directory.is_dir():
            all_files.extend(directory.glob("*.desktop"))
    return all_files


def find_related_desktop_files(
    exec_path: str,
    executables: list[str],
    all_desktop_files: list[Path],
) -> list[Path]:
    """
    Find all .desktop files that reference the given program.

    This searches through all desktop files for Exec entries that match
    any of the executable names provided.

    Args:
        exec_path: Full path to the executable (currently unused, kept for compatibility)
        executables: List of executable names to search for
        all_desktop_files: List of .desktop file paths to search through

    Returns:
        List of .desktop files that reference the executables
    """
    found_files: set[Path] = set()
    search_terms = set(executables)

    for desktop_file in all_desktop_files:
        try:
            content = desktop_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("Exec="):
                    command_str = line.split("=", 1)[1].strip()
                    if not command_str:
                        continue  # Handle empty Exec=
                    executable_in_file = command_str.split()[0]

                    if Path(executable_in_file).name in search_terms:
                        found_files.add(desktop_file)
                        break
        except (IOError, UnicodeDecodeError):
            continue

    return list(found_files)
