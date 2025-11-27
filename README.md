# Waylandify

A tool to add Wayland support for Chromium-based (browser/electron) apps by automatically adding necessary command-line flags to desktop files.

Waylandify intelligently modifies `.desktop` files to enable Wayland support without touching system files. It works by:
- Creating modified copies in `~/.local/share/applications/` (user-level desktop files)
- Automatically backing up any existing files before modification
- Parsing command arguments intelligently to avoid duplicating flags
- Providing easy restoration to revert changes

## Features

- **Smart Flag Parsing**: Properly handles various command-line flag formats (`--flag=value`, `--flag value`, `-f`, `%F`, etc.)
- **Duplicate Prevention**: Automatically detects and skips flags that are already present
- **Feature Merging**: Intelligently merges `--enable-features` flags (Chromium-style)
- **Safe Modifications**: Never modifies system files, only user-level desktop files
- **Automatic Backups**: Creates timestamped backups before any modifications
- **Easy Restoration**: Restore from backups or revert to system defaults with a single command
- **Dry-Run Mode**: Preview changes before applying them
- **Diff View**: See exactly what changes would be made
- **Configurable**: Define multiple programs with different flag sets
- **Flatpak/Snap Support**: Discovers desktop files from Flatpak and Snap installations
- **XDG Compliant**: Respects `XDG_CONFIG_HOME` and `XDG_DATA_HOME` environment variables

## Installation

Use astral/uv to install via git.

## Quick Start

1. **Initialize configuration**:
   ```bash
   waylandify init
   ```

2. **Edit the configuration file** at `~/.config/waylandify/config.toml` to add your programs

3. **Preview changes** (dry-run mode):
   ```bash
   waylandify apply --dry-run
   ```

4. **Apply changes**:
   ```bash
   waylandify apply
   ```

## Usage

### Commands

#### `waylandify init`

Creates a default configuration file at `~/.config/waylandify/config.toml`.

#### `waylandify apply`

Applies Wayland flags to the applications defined in the config file.

**Options**:
- `--dry-run`, `-n`: Preview what would be changed without making any modifications

**Example**:
```bash
# Preview changes
waylandify apply --dry-run

# Apply changes
waylandify apply
```

#### `waylandify list`

Lists all configured programs and their associated desktop files.

```bash
waylandify list
```

#### `waylandify status`

Shows the current status of waylandify modifications, including:
- Configuration file location and validity
- Modified desktop files
- Available backups

```bash
waylandify status
```

#### `waylandify diff`

Shows what changes would be made to desktop files in a unified diff format.

```bash
# Show all diffs
waylandify diff

# Show diff for specific program
waylandify diff "Electron Apps"
```

#### `waylandify restore`

Restore desktop files from backups or revert to system defaults.

**Usage**:
```bash
# List available backups
waylandify restore

# Restore from a specific backup
waylandify restore backup_20250126_123456_789012

# Remove modified files and use system defaults
waylandify restore --remove-only
```

### Configuration File

The configuration file uses TOML format and is located at `~/.config/waylandify/config.toml` (or `$XDG_CONFIG_HOME/waylandify/config.toml` if set).

**Structure**:
- `[[programs]]`: Define multiple program entries
  - `name`: A descriptive name for this entry
  - `executables`: List of executable names to search for (e.g., `["code", "code-insiders"]`)
  - `flags`: List of command-line flags to add
  - `enabled`: (optional) Set to `false` to skip this entry. Default: `true`
  - `merge_enable_features`: (optional) Merge `--enable-features` flags. Default: `true`

**Example**:
```toml
[[programs]]
name = "VS Code"
executables = ["code", "code-insiders", "code-oss"]
flags = [
    "--enable-features=UseOzonePlatform",
    "--ozone-platform=wayland",
    "--enable-features=WaylandWindowDecorations",
]

[[programs]]
name = "Chromium Browsers"
executables = ["brave-browser", "google-chrome", "chromium"]
flags = [
    "--enable-features=TouchpadOverscrollHistoryNavigation",
    "--gtk-version=4",
]

# Disabled entry example
[[programs]]
name = "Disabled App"
executables = ["some-app"]
flags = ["--some-flag"]
enabled = false
```

### Feature Merging

Waylandify automatically merges multiple `--enable-features` flags into a single flag, as Chromium-based applications expect. For example:

```toml
flags = [
    "--enable-features=UseOzonePlatform",
    "--enable-features=WaylandWindowDecorations",
]
```

Will be merged into:
```
--enable-features=UseOzonePlatform,WaylandWindowDecorations
```

This behavior can be disabled per-program by setting `merge_enable_features = false`.

## How It Works

1. **Indexing**: Waylandify first scans standard directories (including Flatpak and Snap locations) to build an efficient index of all `.desktop` files. This index maps the executable names found in their `Exec=` lines to the corresponding desktop file paths.

2. **Matching**: For each program defined in your `config.toml`, Waylandify uses this index to find all `.desktop` files that reference any of the specified executables.

3. **Parsing**: Uses a sophisticated parser to understand existing command arguments within the matched desktop files.

4. **Modification**: Adds new flags intelligently, avoiding duplicates and merging `--enable-features` flags.

5. **Backup**: Creates timestamped backups before any changes.

6. **Application**: Writes modified desktop files to `~/.local/share/applications/`

## Safety and Backups

Waylandify is designed to be safe:

- **Never modifies system files**: Only creates/modifies files in `~/.local/share/applications/`
- **Automatic backups**: Every modification creates a timestamped backup in `~/.config/waylandify/backups/`
- **Metadata tracking**: Keeps a record of all modifications in `metadata.json`
- **Easy restoration**: Multiple options to revert changes

### Backup Locations

- **Backups**: `~/.config/waylandify/backups/backup_TIMESTAMP/`
- **Metadata**: `~/.config/waylandify/backups/metadata.json`
- **Modified files**: `~/.local/share/applications/*.desktop`

### Restoring Changes

Three ways to revert modifications:

1. **Restore from specific backup**:
   ```bash
   waylandify restore backup_20250126_123456_789012
   ```

2. **Remove modified files** (system will use original desktop files):
   ```bash
   waylandify restore --remove-only
   ```

3. **Manual restoration**: Copy files from backup directory manually

## Supported Desktop File Locations

Waylandify searches for desktop files in the following locations:

- `/usr/share/applications` - System applications
- `/usr/local/share/applications` - Locally installed applications
- `~/.local/share/applications` - User applications
- `/var/lib/flatpak/exports/share/applications` - System Flatpak apps
- `~/.local/share/flatpak/exports/share/applications` - User Flatpak apps
- `/var/lib/snapd/desktop/applications` - Snap applications
- Directories from `$XDG_DATA_DIRS`

## Common Wayland Flags

### Chromium-based Applications

```toml
flags = [
    "--enable-features=UseOzonePlatform",
    "--ozone-platform=wayland",
    "--enable-features=WaylandWindowDecorations",
]
```

### Electron Applications

```toml
flags = [
    "--enable-features=UseOzonePlatform",
    "--ozone-platform=wayland",
    "--enable-features=WaylandWindowDecorations",
]
```

### GTK Version

```toml
flags = ["--gtk-version=4"]
```

### Touchpad Gestures (Chromium)

```toml
flags = ["--enable-features=TouchpadOverscrollHistoryNavigation"]
```

## Troubleshooting

### Changes not taking effect

After applying changes, you may need to:
- Log out and log back in
- Restart your desktop environment
- Update the desktop database: `update-desktop-database ~/.local/share/applications`

### Desktop file not found

If waylandify can't find the desktop file:
1. Run `waylandify list` to see what's detected
2. Check if the executable is in your PATH: `which <executable-name>`
3. Manually search for desktop files: `find /usr/share/applications ~/.local/share/applications -name "*.desktop"`
4. Verify the executable name in the desktop file matches your config

### Flags not working

Some applications may require specific flag combinations. Check the application's documentation for recommended Wayland flags.

## Development

### Architecture

The project is organized into modules:

- **cli.py**: Command-line interface using Typer
- **config.py**: Configuration file management with Pydantic validation
- **desktop.py**: Desktop file parsing and modification
- **exec_parser.py**: Intelligent Exec command parsing and flag management
- **discovery.py**: Executable and desktop file discovery
- **backup.py**: Backup creation and restoration

### Running from Source

```bash
# Install development dependencies
uv sync

# Run the CLI
uv run waylandify --help

# Run with a specific command
uv run waylandify status
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source. See LICENSE file for details.

## Credits

Created by Jassiel Ovando
