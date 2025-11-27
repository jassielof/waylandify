"""
Desktop file discovery and executable path resolution.

This module provides utilities for finding executables in the system PATH
and locating related .desktop files that reference those executables.
"""

import os
import shutil
import re
from collections import defaultdict
from pathlib import Path

from .config import XDG_DATA_HOME

# Standard directories where .desktop files are stored
DESKTOP_FILE_DIRS = [
    # System directories
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    # User directory (XDG compliant)
    XDG_DATA_HOME / "applications",
    # Flatpak directories
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
    # Snap directory
    Path("/var/lib/snapd/desktop/applications"),
]


def get_desktop_file_dirs() -> list[Path]:
    """
    Get all desktop file directories, including XDG_DATA_DIRS.

    Returns:
        List of paths to search for .desktop files
    """
    dirs = list(DESKTOP_FILE_DIRS)

    # Add directories from XDG_DATA_DIRS environment variable
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for data_dir in xdg_data_dirs.split(":"):
        app_dir = Path(data_dir) / "applications"
        if app_dir not in dirs:
            dirs.append(app_dir)

    return dirs


class DesktopFileIndexer:
    """
    Indexes .desktop files by their executable names for efficient lookup.
    """

    def __init__(self, desktop_file_dirs: list[Path] | None = None):
        self._desktop_files_by_executable: dict[str, list[Path]] = defaultdict(list)
        self.desktop_file_dirs = (
            desktop_file_dirs if desktop_file_dirs is not None else get_desktop_file_dirs()
        )
        self._index_desktop_files()

    def _index_desktop_files(self) -> None:
        """
        Scans specified directories for .desktop files and builds an index
        mapping executable names to lists of desktop file paths.
        """
        all_desktop_files = self._get_all_desktop_files()
        for desktop_file in all_desktop_files:
            exec_name = self._extract_executable_name(desktop_file)
            if exec_name:
                self._desktop_files_by_executable[exec_name].append(desktop_file)

    def _get_all_desktop_files(self) -> list[Path]:
        """
        Scan standard directories and return a list of all .desktop files.
        """
        all_files = []
        seen_files = set()  # Avoid duplicates from overlapping directories

        for directory in self.desktop_file_dirs:
            if directory.is_dir():
                for desktop_file in directory.glob("*.desktop"):
                    if desktop_file.name not in seen_files:
                        all_files.append(desktop_file)
                        seen_files.add(desktop_file.name)

        return all_files

    def _extract_executable_name(self, desktop_file_path: Path) -> str | None:
        """
        Extracts the executable name from the Exec= line of a .desktop file.
        Handles cases where Exec= might contain arguments or full paths.
        """
        try:
            content = desktop_file_path.read_text()
            for line in content.splitlines():
                line = line.strip()
                # Handle "Exec= command" and "Exec=command" and "Exec = command"
                if line.lower().startswith("exec="):
                    command_str = line.split("=", 1)[1].strip()
                    if not command_str:
                        return None  # Empty Exec=
                    # Use a regex to get the first "word" before any spaces, quotes or %-codes
                    # This handles:
                    # Exec=brave-browser %U
                    # Exec=/opt/microsoft/msedge/microsoft-edge %U
                    # Exec="brave-browser" %U
                    # Exec="electron" /path/to/app
                    # Exec=env VAR=value command (skip env prefix)
                    # Exec=/usr/bin/flatpak run com.app.Name (handle flatpak)

                    # Skip 'env' command prefix
                    if command_str.startswith("env "):
                        # Find the actual command after env vars
                        parts = command_str.split()
                        for i, part in enumerate(parts[1:], 1):
                            if "=" not in part:
                                command_str = " ".join(parts[i:])
                                break

                    match = re.match(r'^"?([^"\s]+)"?', command_str)
                    if match:
                        exec_full_path = match.group(1)
                        return Path(exec_full_path).name  # Return just the executable name
                    return None
        except (IOError, UnicodeDecodeError):
            return None
        return None

    def get_desktop_files_for_executables(
        self, executable_names: list[str]
    ) -> list[Path]:
        """
        Retrieves all .desktop files associated with the given executable names from the index.
        """
        found_files: set[Path] = set()
        for name in executable_names:
            if name in self._desktop_files_by_executable:
                found_files.update(self._desktop_files_by_executable[name])
        return list(found_files)

    def get_all_indexed_executables(self) -> list[str]:
        """
        Get all executable names that have been indexed.

        Returns:
            Sorted list of executable names
        """
        return sorted(self._desktop_files_by_executable.keys())


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
