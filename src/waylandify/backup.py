"""
Backup and restoration utilities for desktop files.

This module handles creating backups of desktop files before modification,
tracking all modifications made by waylandify, and restoring them when requested.
"""

import datetime
import json
import shutil
from pathlib import Path

from rich import print as rprint

from .config import BACKUP_DIR, get_user_desktop_dir

BACKUP_METADATA_FILE = BACKUP_DIR / "metadata.json"


def _load_metadata() -> dict:
    """Load metadata from JSON file."""
    if not BACKUP_METADATA_FILE.exists():
        return {"backups": [], "modifications": []}

    try:
        data = json.loads(BACKUP_METADATA_FILE.read_text())
        # Ensure both keys exist for backwards compatibility
        if "modifications" not in data:
            data["modifications"] = []
        return data
    except (json.JSONDecodeError, IOError):
        return {"backups": [], "modifications": []}


def _save_metadata(metadata: dict) -> None:
    """Save metadata to JSON file."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_METADATA_FILE.write_text(json.dumps(metadata, indent=2))
    except IOError as e:
        rprint(f"[yellow]⚠️  Could not save metadata: {e}[/yellow]")


# Backwards compatibility alias
_load_backup_metadata = _load_metadata
_save_backup_metadata = _save_metadata


def record_modification(
    target_path: Path,
    source_path: Path,
    program_name: str,
    flags_applied: list[str],
) -> None:
    """
    Record a file modification in the metadata.

    Args:
        target_path: Path to the modified file
        source_path: Original source file path
        program_name: Name of the program configuration
        flags_applied: List of flags that were applied
    """
    metadata = _load_metadata()

    # Check if this file is already tracked
    existing = next(
        (m for m in metadata["modifications"] if m["target_path"] == str(target_path)),
        None,
    )

    timestamp = datetime.datetime.now().isoformat()

    if existing:
        # Update existing record
        existing["last_modified"] = timestamp
        existing["flags_applied"] = flags_applied
        existing["program_name"] = program_name
    else:
        # Add new record
        metadata["modifications"].append(
            {
                "target_path": str(target_path),
                "source_path": str(source_path),
                "program_name": program_name,
                "flags_applied": flags_applied,
                "created": timestamp,
                "last_modified": timestamp,
            }
        )

    _save_metadata(metadata)


def get_modified_files() -> list[dict]:
    """
    Get list of all files modified by waylandify.

    Returns:
        List of modification records
    """
    metadata = _load_metadata()
    modifications = metadata.get("modifications", [])

    # Filter to only existing files
    existing = []
    for mod in modifications:
        if Path(mod["target_path"]).exists():
            existing.append(mod)

    return existing


def is_file_modified_by_waylandify(file_path: Path) -> bool:
    """
    Check if a file was modified by waylandify.

    Args:
        file_path: Path to check

    Returns:
        True if the file is tracked as modified by waylandify
    """
    metadata = _load_metadata()
    for mod in metadata.get("modifications", []):
        if mod["target_path"] == str(file_path):
            return True
    return False


def remove_modification_record(file_path: Path) -> bool:
    """
    Remove a file from the modifications tracking.

    Args:
        file_path: Path of the file to untrack

    Returns:
        True if the record was removed
    """
    metadata = _load_metadata()
    original_count = len(metadata.get("modifications", []))
    metadata["modifications"] = [
        m for m in metadata.get("modifications", []) if m["target_path"] != str(file_path)
    ]
    _save_metadata(metadata)
    return len(metadata["modifications"]) < original_count


def create_backup(file_path: Path) -> Path | None:
    """
    Creates a timestamped backup of a file.

    Args:
        file_path: Path to the file to backup

    Returns:
        Path to the backup file, or None on failure
    """
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_subdir = BACKUP_DIR / f"backup_{timestamp}"
        backup_subdir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_subdir / file_path.name
        shutil.copy2(file_path, backup_path)

        # Record backup metadata
        metadata = _load_metadata()
        metadata["backups"].append(
            {
                "timestamp": timestamp,
                "original_path": str(file_path),
                "backup_path": str(backup_path),
                "backup_dir": str(backup_subdir),
            }
        )
        _save_metadata(metadata)

        return backup_path
    except Exception as e:
        rprint(f"[yellow]⚠️  Could not create backup for {file_path}: {e}[/yellow]")
        return None


def list_backups() -> list[dict]:
    """
    List all available backups.

    Returns:
        List of backup metadata dictionaries
    """
    metadata = _load_metadata()
    return metadata.get("backups", [])


def restore_from_backup(backup_dir: str | Path) -> bool:
    """
    Restore files from a specific backup directory.

    Args:
        backup_dir: Path to the backup directory to restore from

    Returns:
        True if restoration was successful, False otherwise
    """
    backup_dir = Path(backup_dir)

    if not backup_dir.exists() or not backup_dir.is_dir():
        rprint(f"[bold red]❌ Backup directory not found: {backup_dir}[/bold red]")
        return False

    metadata = _load_metadata()
    backups = [b for b in metadata.get("backups", []) if b["backup_dir"] == str(backup_dir)]

    if not backups:
        rprint(f"[bold red]❌ No metadata found for backup directory: {backup_dir}[/bold red]")
        return False

    success = True
    for backup_info in backups:
        backup_path = Path(backup_info["backup_path"])
        original_path = Path(backup_info["original_path"])

        if not backup_path.exists():
            rprint(f"[yellow]⚠️  Backup file not found: {backup_path}[/yellow]")
            success = False
            continue

        try:
            shutil.copy2(backup_path, original_path)
            rprint(f"[green]✅ Restored: {original_path}[/green]")
        except Exception as e:
            rprint(f"[bold red]❌ Failed to restore {original_path}: {e}[/bold red]")
            success = False

    return success


def remove_user_desktop_files() -> int:
    """
    Remove all user desktop files that were created/modified by waylandify.

    This allows the system to fall back to the original system desktop files.

    Returns:
        Number of files removed
    """
    user_desktop_dir = get_user_desktop_dir()

    if not user_desktop_dir.exists():
        return 0

    metadata = _load_metadata()

    # Get files from both backups and modifications
    tracked_files = set()
    for b in metadata.get("backups", []):
        tracked_files.add(Path(b["original_path"]))
    for m in metadata.get("modifications", []):
        tracked_files.add(Path(m["target_path"]))

    removed_count = 0
    for desktop_file in user_desktop_dir.glob("*.desktop"):
        if desktop_file in tracked_files:
            try:
                desktop_file.unlink()
                rprint(f"[dim]🗑️  Removed: {desktop_file}[/dim]")
                removed_count += 1
            except Exception as e:
                rprint(f"[yellow]⚠️  Could not remove {desktop_file}: {e}[/yellow]")

    # Clear modifications tracking
    if removed_count > 0:
        metadata["modifications"] = []
        _save_metadata(metadata)

    return removed_count


def clear_all_backups() -> bool:
    """
    Remove all backup directories and metadata.

    WARNING: This permanently deletes all backups!

    Returns:
        True if successful, False otherwise
    """
    if not BACKUP_DIR.exists():
        return True

    try:
        shutil.rmtree(BACKUP_DIR)
        rprint("[green]✅ All backups cleared[/green]")
        return True
    except Exception as e:
        rprint(f"[bold red]❌ Failed to clear backups: {e}[/bold red]")
        return False


def clean_old_backups(older_than_days: int) -> tuple[int, int]:
    """
    Remove backup directories older than the specified number of days.

    Args:
        older_than_days: Remove backups older than this many days

    Returns:
        Tuple of (directories_removed, files_removed)
    """
    if not BACKUP_DIR.exists():
        return 0, 0

    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=older_than_days)
    metadata = _load_metadata()
    backups = metadata.get("backups", [])

    dirs_removed = 0
    files_removed = 0
    dirs_to_remove = set()
    remaining_backups = []

    for backup_info in backups:
        try:
            # Parse timestamp from format: YYYYMMDD_HHMMSS_microseconds
            timestamp_str = backup_info["timestamp"]
            backup_date = datetime.datetime.strptime(timestamp_str[:15], "%Y%m%d_%H%M%S")

            if backup_date < cutoff_date:
                dirs_to_remove.add(backup_info["backup_dir"])
                files_removed += 1
            else:
                remaining_backups.append(backup_info)
        except (KeyError, ValueError):
            # Keep backups we can't parse
            remaining_backups.append(backup_info)

    # Remove old backup directories
    for backup_dir_str in dirs_to_remove:
        backup_dir_path = Path(backup_dir_str)
        if backup_dir_path.exists():
            try:
                shutil.rmtree(backup_dir_path)
                dirs_removed += 1
                rprint(f"[dim]🗑️  Removed: {backup_dir_path.name}[/dim]")
            except Exception as e:
                rprint(f"[yellow]⚠️  Could not remove {backup_dir_path}: {e}[/yellow]")

    # Update metadata
    metadata["backups"] = remaining_backups
    _save_metadata(metadata)

    return dirs_removed, files_removed


def get_backup_stats() -> dict:
    """
    Get statistics about backups and modifications.

    Returns:
        Dictionary with backup and modification statistics
    """
    metadata = _load_metadata()
    backups = metadata.get("backups", [])
    modifications = metadata.get("modifications", [])

    # Count existing modified files
    existing_modifications = [m for m in modifications if Path(m["target_path"]).exists()]

    if not backups and not existing_modifications:
        return {
            "total_backups": 0,
            "total_dirs": 0,
            "total_modifications": 0,
            "oldest": None,
            "newest": None,
        }

    backup_dirs = set(b["backup_dir"] for b in backups)

    # Find oldest and newest from backups
    timestamps = []
    for b in backups:
        try:
            ts = datetime.datetime.strptime(b["timestamp"][:15], "%Y%m%d_%H%M%S")
            timestamps.append(ts)
        except (KeyError, ValueError):
            pass

    return {
        "total_backups": len(backups),
        "total_dirs": len(backup_dirs),
        "total_modifications": len(existing_modifications),
        "oldest": min(timestamps) if timestamps else None,
        "newest": max(timestamps) if timestamps else None,
    }
