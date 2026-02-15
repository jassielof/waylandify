from pathlib import Path

import xdg_desktop_entry as xde
from xdg_desktop_entry.desktop_file import DesktopEntryDocument, Section
from xdg_desktop_entry.exec import add_flags, sync_flags

LOAD_DOCUMENT = getattr(xde, "load_document")
FORMAT_DOCUMENT = getattr(xde, "format_document")


def _load_exec_value(path: Path) -> tuple[str, DesktopEntryDocument, Section, str]:
    original_content = path.read_text()
    document = LOAD_DOCUMENT(path)
    section = document.desktop_entry

    if section is None:
        raise ValueError("Missing [Desktop Entry] section")

    exec_value = section.get("Exec")
    if not exec_value:
        raise ValueError("Missing Exec entry in [Desktop Entry]")

    return original_content, document, section, exec_value


def sync_flags_in_file(
    path: Path,
    desired_flags: list[str],
    previous_flags: list[str] | None,
    *,
    merge_enable_features: bool,
) -> tuple[str, bool]:
    original_content, document, section, exec_value = _load_exec_value(path)

    updated_exec, _ = sync_flags(
        exec_value,
        desired_flags,
        previous_flags or [],
        merge_enable_features=merge_enable_features,
    )

    section.set("Exec", updated_exec)
    modified_content = FORMAT_DOCUMENT(
        document,
        sort_sections=False,
        sort_entries=False,
    )

    return modified_content, modified_content != original_content


def preview_add_flags_in_file(
    path: Path,
    desired_flags: list[str],
    *,
    merge_enable_features: bool,
) -> tuple[str, bool]:
    original_content, document, section, exec_value = _load_exec_value(path)

    updated_exec, _ = add_flags(
        exec_value,
        desired_flags,
        merge_enable_features=merge_enable_features,
    )

    section.set("Exec", updated_exec)
    modified_content = FORMAT_DOCUMENT(
        document,
        sort_sections=False,
        sort_entries=False,
    )

    return modified_content, modified_content != original_content
