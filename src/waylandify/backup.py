"""
Backup and restoration utilities for desktop files.

This module handles creating backups of desktop files before modification
and restoring them when requested.
"""

import datetime
import json
import shutil
from pathlib import Path

from .config import BACKUP_DIR

BACKUP_METADATA_FILE = BACKUP_DIR / "metadata.json"


def _load_backup_metadata() -> dict:
    """Load backup metadata from JSON file."""
    if not BACKUP_METADATA_FILE.exists():
        return {"backups": []}

    try:
        return json.loads(BACKUP_METADATA_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return {"backups": []}


def _save_backup_metadata(metadata: dict) -> None:
    """Save backup metadata to JSON file."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_METADATA_FILE.write_text(json.dumps(metadata, indent=2))
    except IOError as e:
        print(f"⚠️  Could not save backup metadata: {e}")


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
        metadata = _load_backup_metadata()
        metadata["backups"].append(
            {
                "timestamp": timestamp,
                "original_path": str(file_path),
                "backup_path": str(backup_path),
                "backup_dir": str(backup_subdir),
            }
        )
        _save_backup_metadata(metadata)

        return backup_path
    except Exception as e:
        print(f"⚠️  Could not create backup for {file_path}: {e}")
        return None


def list_backups() -> list[dict]:
    """
    List all available backups.

    Returns:
        List of backup metadata dictionaries
    """
    metadata = _load_backup_metadata()
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
        print(f"❌ Backup directory not found: {backup_dir}")
        return False

    metadata = _load_backup_metadata()
    backups = [b for b in metadata.get("backups", []) if b["backup_dir"] == str(backup_dir)]

    if not backups:
        print(f"❌ No metadata found for backup directory: {backup_dir}")
        return False

    success = True
    for backup_info in backups:
        backup_path = Path(backup_info["backup_path"])
        original_path = Path(backup_info["original_path"])

        if not backup_path.exists():
            print(f"⚠️  Backup file not found: {backup_path}")
            success = False
            continue

        try:
            shutil.copy2(backup_path, original_path)
            print(f"✅ Restored: {original_path}")
        except Exception as e:
            print(f"❌ Failed to restore {original_path}: {e}")
            success = False

    return success


def remove_user_desktop_files() -> int:
    """
    Remove all user desktop files that were created by waylandify.

    This allows the system to fall back to the original system desktop files.

    Returns:
        Number of files removed
    """
    user_desktop_dir = Path.home() / ".local/share/applications"

    if not user_desktop_dir.exists():
        return 0

    metadata = _load_backup_metadata()
    backed_up_files = {Path(b["original_path"]) for b in metadata.get("backups", [])}

    removed_count = 0
    for desktop_file in user_desktop_dir.glob("*.desktop"):
        if desktop_file in backed_up_files:
            try:
                desktop_file.unlink()
                print(f"🗑️  Removed: {desktop_file}")
                removed_count += 1
            except Exception as e:
                print(f"⚠️  Could not remove {desktop_file}: {e}")

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
        print("✅ All backups cleared")
        return True
    except Exception as e:
        print(f"❌ Failed to clear backups: {e}")
        return False
