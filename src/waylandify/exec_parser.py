"""
Parser for Desktop Entry Exec key format.

This module provides functionality to parse, manipulate, and compare
Exec command strings from .desktop files according to the Desktop Entry
Specification.

References:
- https://specifications.freedesktop.org/desktop-entry-spec/latest/
"""

import re
import shlex
from dataclasses import dataclass
from enum import Enum

from rich import print as rprint


class ArgumentType(Enum):
    """Types of arguments found in Exec commands."""

    EXECUTABLE = "executable"
    LONG_FLAG = "long_flag"  # --flag or --flag=value
    SHORT_FLAG = "short_flag"  # -f or -f value
    FIELD_CODE = "field_code"  # %f, %F, %u, %U, etc.
    VALUE = "value"  # standalone value or argument


@dataclass
class ExecArgument:
    """Represents a single argument in an Exec command."""

    type: ArgumentType
    value: str
    attached_value: str | None = None  # For --flag=value format

    def __str__(self) -> str:
        """Return the string representation of this argument."""
        if self.attached_value is not None:
            return f"{self.value}={self.attached_value}"
        return self.value

    def __eq__(self, other) -> bool:
        """Check equality based on type and value, ignoring attached values for long flags."""
        if not isinstance(other, ExecArgument):
            return False
        if self.type != other.type:
            return False
        # For long flags, consider --flag and --flag=value as the same flag
        if self.type == ArgumentType.LONG_FLAG:
            return self.value == other.value
        return self.value == other.value and self.attached_value == other.attached_value


@dataclass
class ExecCommand:
    """Represents a parsed Exec command from a .desktop file."""

    executable: str
    arguments: list[ExecArgument]

    def __str__(self) -> str:
        """Reconstruct the full command string."""
        parts = [self.executable]
        parts.extend(str(arg) for arg in self.arguments)
        return " ".join(parts)

    def has_flag(self, flag: str) -> bool:
        """
        Check if a flag exists in the command.

        Args:
            flag: The flag to check (e.g., "--ozone-platform", "-f")

        Returns:
            True if the flag exists, False otherwise
        """
        # Handle both --flag and --flag=value formats
        flag_base = flag.split("=")[0] if "=" in flag else flag

        for arg in self.arguments:
            if arg.type in (ArgumentType.LONG_FLAG, ArgumentType.SHORT_FLAG):
                if arg.value == flag_base:
                    return True
        return False

    def get_enable_features(self) -> list[str]:
        """
        Get all features from --enable-features flags.

        Returns:
            List of feature names
        """
        features = []
        for arg in self.arguments:
            if arg.type == ArgumentType.LONG_FLAG and arg.value == "--enable-features":
                if arg.attached_value:
                    features.extend(arg.attached_value.split(","))
        return features

    def add_flag(self, flag: str, merge_enable_features: bool = True) -> bool:
        """
        Add a flag to the command if it doesn't already exist.

        For --enable-features flags, merges the features into an existing
        --enable-features flag if merge_enable_features is True.

        Args:
            flag: The flag to add (e.g., "--ozone-platform=wayland", "-f value")
            merge_enable_features: If True, merge --enable-features values

        Returns:
            True if the flag was added or modified, False if it already exists
        """
        # Special handling for --enable-features
        if merge_enable_features and flag.startswith("--enable-features="):
            new_features = flag.split("=", 1)[1].split(",")
            existing_features = self.get_enable_features()

            # Check if all new features already exist
            features_to_add = [f for f in new_features if f not in existing_features]
            if not features_to_add:
                return False

            # Find existing --enable-features argument and merge
            for arg in self.arguments:
                if (
                    arg.type == ArgumentType.LONG_FLAG
                    and arg.value == "--enable-features"
                ):
                    if arg.attached_value:
                        arg.attached_value = ",".join(
                            existing_features + features_to_add
                        )
                    else:
                        arg.attached_value = ",".join(features_to_add)
                    return True

            # No existing --enable-features, add new one
            parsed_arg = _parse_single_argument(flag)
            self.arguments.insert(0, parsed_arg)
            return True

        if self.has_flag(flag):
            return False

        # Parse the flag to add
        parsed_arg = _parse_single_argument(flag)
        self.arguments.insert(0, parsed_arg)  # Add new flags at the beginning
        return True

    def remove_flag(self, flag: str) -> bool:
        """
        Remove a flag from the command if it exists.

        For --enable-features flags, removes individual features from the
        combined --enable-features argument.

        Args:
            flag: The flag to remove (e.g., "--ozone-platform=wayland")

        Returns:
            True if the flag was removed, False if not found
        """
        # Special handling for --enable-features
        if flag.startswith("--enable-features="):
            features_to_remove = set(flag.split("=", 1)[1].split(","))

            for arg in self.arguments:
                if (
                    arg.type == ArgumentType.LONG_FLAG
                    and arg.value == "--enable-features"
                    and arg.attached_value
                ):
                    existing = arg.attached_value.split(",")
                    remaining = [f for f in existing if f not in features_to_remove]

                    if len(remaining) < len(existing):
                        if remaining:
                            arg.attached_value = ",".join(remaining)
                        else:
                            # Remove the entire --enable-features argument
                            self.arguments.remove(arg)
                        return True
            return False

        # Handle regular flags
        flag_base = flag.split("=")[0] if "=" in flag else flag

        for arg in self.arguments:
            if arg.type in (ArgumentType.LONG_FLAG, ArgumentType.SHORT_FLAG):
                if arg.value == flag_base:
                    self.arguments.remove(arg)
                    return True
        return False

    def get_flag_value(self, flag: str) -> str | None:
        """
        Get the value associated with a flag.

        Args:
            flag: The flag to look for (e.g., "--ozone-platform")

        Returns:
            The flag's value if found, None otherwise
        """
        flag_base = flag.split("=")[0] if "=" in flag else flag

        for i, arg in enumerate(self.arguments):
            if arg.type == ArgumentType.LONG_FLAG and arg.value == flag_base:
                if arg.attached_value:
                    return arg.attached_value
                # Check if next argument is the value
                if i + 1 < len(self.arguments):
                    next_arg = self.arguments[i + 1]
                    if next_arg.type == ArgumentType.VALUE:
                        return next_arg.value
                return None
            elif arg.type == ArgumentType.SHORT_FLAG and arg.value == flag_base:
                # For short flags, value is typically the next argument
                if i + 1 < len(self.arguments):
                    next_arg = self.arguments[i + 1]
                    if next_arg.type == ArgumentType.VALUE:
                        return next_arg.value
                return None

        return None


def _parse_single_argument(arg: str) -> ExecArgument:
    """
    Parse a single argument and determine its type.

    Args:
        arg: A single argument string

    Returns:
        An ExecArgument object
    """
    # Field codes: %f, %F, %u, %U, etc.
    if re.match(r"^%[a-zA-Z]$", arg):
        return ExecArgument(type=ArgumentType.FIELD_CODE, value=arg)

    # Long flags: --flag or --flag=value
    if arg.startswith("--"):
        if "=" in arg:
            flag, value = arg.split("=", 1)
            return ExecArgument(
                type=ArgumentType.LONG_FLAG, value=flag, attached_value=value
            )
        return ExecArgument(type=ArgumentType.LONG_FLAG, value=arg)

    # Short flags: -f
    if arg.startswith("-") and len(arg) >= 2 and not arg[1].isdigit():
        return ExecArgument(type=ArgumentType.SHORT_FLAG, value=arg)

    # Everything else is a value
    return ExecArgument(type=ArgumentType.VALUE, value=arg)


def parse_exec_command(exec_string: str) -> ExecCommand:
    """
    Parse an Exec command string from a .desktop file.

    Args:
        exec_string: The full Exec command string

    Returns:
        An ExecCommand object

    Raises:
        ValueError: If the exec_string is empty or invalid
    """
    if not exec_string or not exec_string.strip():
        raise ValueError("Exec command string cannot be empty")

    # Use shlex to properly handle quoted strings and special characters
    try:
        parts = shlex.split(exec_string)
    except ValueError as e:
        # Fallback to simple split if shlex fails
        rprint(
            f"[yellow]Warning: shlex failed to parse exec string: {e}. Falling back to simple split.[/yellow]"
        )
        parts = exec_string.split()

    if not parts:
        raise ValueError("Exec command string is invalid")

    executable = parts[0]
    arguments = [_parse_single_argument(arg) for arg in parts[1:]]

    return ExecCommand(executable=executable, arguments=arguments)


def add_flags_to_exec(
    exec_string: str, flags: list[str], merge_enable_features: bool = True
) -> tuple[str, bool]:
    """
    Add flags to an Exec command string, avoiding duplicates.

    Args:
        exec_string: The original Exec command string
        flags: List of flags to add
        merge_enable_features: If True, merge --enable-features values instead
            of adding duplicate flags

    Returns:
        A tuple of (modified_command_string, was_modified)
        where was_modified is True if any flags were added
    """
    if not exec_string or not exec_string.strip():
        return "", False

    try:
        cmd = parse_exec_command(exec_string)
    except ValueError:
        # If parsing fails, return original
        return exec_string, False

    modified = False
    for flag in flags:
        if cmd.add_flag(flag, merge_enable_features=merge_enable_features):
            modified = True

    return str(cmd), modified


def remove_flags_from_exec(
    exec_string: str, flags: list[str]
) -> tuple[str, bool]:
    """
    Remove flags from an Exec command string.

    Args:
        exec_string: The original Exec command string
        flags: List of flags to remove

    Returns:
        A tuple of (modified_command_string, was_modified)
        where was_modified is True if any flags were removed
    """
    if not exec_string or not exec_string.strip():
        return "", False

    try:
        cmd = parse_exec_command(exec_string)
    except ValueError:
        return exec_string, False

    modified = False
    for flag in flags:
        if cmd.remove_flag(flag):
            modified = True

    return str(cmd), modified


def sync_flags_to_exec(
    exec_string: str,
    desired_flags: list[str],
    previous_flags: list[str],
    merge_enable_features: bool = True,
) -> tuple[str, bool]:
    """
    Synchronize flags in an Exec command to match the desired set.

    Removes flags that were previously applied but are no longer desired,
    then adds any new desired flags.

    Args:
        exec_string: The original Exec command string
        desired_flags: List of flags that should be present
        previous_flags: List of flags that were previously applied (to remove if not in desired)
        merge_enable_features: If True, merge --enable-features values

    Returns:
        A tuple of (modified_command_string, was_modified)
    """
    if not exec_string or not exec_string.strip():
        return "", False

    try:
        cmd = parse_exec_command(exec_string)
    except ValueError:
        return exec_string, False

    modified = False

    # Normalize flags for comparison
    desired_set = set(desired_flags)

    # Remove previously applied flags that are no longer desired
    for flag in previous_flags:
        if flag not in desired_set:
            if cmd.remove_flag(flag):
                modified = True

    # Add any new desired flags
    for flag in desired_flags:
        if cmd.add_flag(flag, merge_enable_features=merge_enable_features):
            modified = True

    return str(cmd), modified


def compare_exec_commands(cmd1: str, cmd2: str) -> bool:
    """
    Compare two Exec command strings to see if they are functionally equivalent.

    Args:
        cmd1: First command string
        cmd2: Second command string

    Returns:
        True if commands are equivalent, False otherwise
    """
    try:
        parsed1 = parse_exec_command(cmd1)
        parsed2 = parse_exec_command(cmd2)

        if parsed1.executable != parsed2.executable:
            return False

        # Compare arguments (order-independent for flags, but order-dependent for values)
        # This is a simplified comparison - you might want to make it more sophisticated
        if len(parsed1.arguments) != len(parsed2.arguments):
            return False

        # For now, do order-dependent comparison
        return parsed1.arguments == parsed2.arguments

    except ValueError:
        # If parsing fails, fall back to string comparison
        return cmd1.strip() == cmd2.strip()


def merge_flags(flags: list[str], merge_enable_features: bool = True) -> list[str]:
    """
    Merge a list of flags, combining --enable-features values.

    This is useful for displaying what flags will actually be applied.

    Args:
        flags: List of flags to merge
        merge_enable_features: If True, combine --enable-features flags

    Returns:
        List of merged flags

    Example:
        >>> merge_flags(["--enable-features=A", "--ozone-platform=wayland", "--enable-features=B"])
        ['--enable-features=A,B', '--ozone-platform=wayland']
    """
    if not merge_enable_features:
        return flags

    enable_features: list[str] = []
    other_flags: list[str] = []

    for flag in flags:
        if flag.startswith("--enable-features="):
            features = flag.split("=", 1)[1].split(",")
            for f in features:
                if f not in enable_features:
                    enable_features.append(f)
        else:
            if flag not in other_flags:
                other_flags.append(flag)

    result = []
    if enable_features:
        result.append(f"--enable-features={','.join(enable_features)}")
    result.extend(other_flags)

    return result


def format_flags_display(flags: list[str], merge_enable_features: bool = True) -> str:
    """
    Format flags for display, merging --enable-features if needed.

    Args:
        flags: List of flags
        merge_enable_features: If True, merge --enable-features flags

    Returns:
        Space-separated string of merged flags
    """
    merged = merge_flags(flags, merge_enable_features)
    return " ".join(merged)
