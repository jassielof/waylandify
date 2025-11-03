# Waylandify

A tool to add Wayland support for Chromium-based (browser/electron) apps.

It creates a config file where you define the programs (desktop files) to be modified with the necessary flags to run in Wayland.

## Installation

Use astral/uv to install via git.

## Usage

Init the config file, modify it as needed, then apply the changes.

### Backups

<!-- TODO: Implement a restore feature, this should allow users to revert their desktop files to the original state. This could simply remove the modified user desktop files and restore the backups, or delete the user ones to simply go back to use the system desktop files. -->
Waylandify shouldn't touch system desktop files, only user desktop files located in `~/.local/share/applications/`. It will always overwrite the user desktop files with the modified versions based on the system desktop files or existing ones (if no system equivalent existed). If you had modified the user desktop files and want to revert it, check for `~/.config/waylandify/backups/` for the pre-overwritten versions.
