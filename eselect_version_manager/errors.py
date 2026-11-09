"""Standard exit codes and exception types for eselect-version-manager."""

import enum


class ExitCode(enum.IntEnum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_USAGE = 2
    UNKNOWN_TOOL = 10
    INVALID_VERSION_CONSTRAINT = 11
    INVALID_CONFIG_SYNTAX = 12
    NO_MATCHING_VERSION = 13
    MISSING_EXECUTABLE = 14
    AMBIGUOUS_PROVIDER = 15
    UNSUPPORTED_VERSION_FILE = 16
    STALE_PROJECT_RECORD = 17
    CONVERSION_CONFLICT = 18
    RECURSION_DETECTED = 19


class VersionManagerError(Exception):
    """Base exception for version manager errors with documented exit code."""

    def __init__(self, message: str, exit_code: ExitCode = ExitCode.GENERAL_ERROR, details: dict = None):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}

    def format_diagnostic(self) -> str:
        """Format human-readable diagnostic output for stderr."""
        lines = [f"eselect-version-manager: {self.message}"]
        if self.details:
            lines.append("")
            col_width = max(len(k) for k in self.details.keys()) + 2
            for key, val in self.details.items():
                if val is not None and str(val).strip():
                    # Format multiline values with indentation
                    val_str = str(val)
                    if "\n" in val_str:
                        lines.append(f"{key.capitalize() + ':':<{col_width}}")
                        for subline in val_str.splitlines():
                            lines.append(f"  {subline}")
                    else:
                        lines.append(f"{key.capitalize() + ':':<{col_width}} {val_str}")
        return "\n".join(lines)


class UnknownToolError(VersionManagerError):
    def __init__(self, tool: str, details: dict = None):
        super().__init__(f"unknown tool '{tool}'", ExitCode.UNKNOWN_TOOL, details)


class InvalidVersionConstraintError(VersionManagerError):
    def __init__(self, tool: str, constraint: str, reason: str = "", details: dict = None):
        d = {"tool": tool, "constraint": constraint}
        if reason:
            d["reason"] = reason
        if details:
            d.update(details)
        super().__init__(f"invalid version constraint '{constraint}' for tool '{tool}'", ExitCode.INVALID_VERSION_CONSTRAINT, d)


class InvalidConfigError(VersionManagerError):
    def __init__(self, path: str, reason: str, details: dict = None):
        d = {"file": path, "reason": reason}
        if details:
            d.update(details)
        super().__init__(f"invalid configuration file: {path}: {reason}", ExitCode.INVALID_CONFIG_SYNTAX, d)


class NoMatchingVersionError(VersionManagerError):
    def __init__(self, tool: str, requested: str, provider: str, installed: list = None, details: dict = None):
        d = {
            "requested": requested,
            "provider": provider,
            "installed": ", ".join(installed) if installed else "none",
        }
        if details:
            d.update(details)
        d["suggestion"] = f"emerge -pv '{provider}'"
        super().__init__(f"cannot resolve {tool}: no installed version satisfies the requested constraint", ExitCode.NO_MATCHING_VERSION, d)


class MissingExecutableError(VersionManagerError):
    def __init__(self, tool: str, command: str, pkg: str, expected_path: str = None, details: dict = None):
        d = {"tool": tool, "command": command, "package": pkg}
        if expected_path:
            d["expected_path"] = expected_path
        if details:
            d.update(details)
        super().__init__(f"executable '{command}' not found in selected package '{pkg}'", ExitCode.MISSING_EXECUTABLE, d)


class StaleProjectRecordError(VersionManagerError):
    def __init__(self, project_id: str, recorded_root: str, current_root: str = None, details: dict = None):
        d = {"project_id": project_id, "recorded_root": recorded_root}
        if current_root:
            d["current_root"] = current_root
            d["suggestion"] = f"eselect version-manager rebind '{recorded_root}' '{current_root}'"
        if details:
            d.update(details)
        super().__init__(f"stale or invalid private project record for '{recorded_root}'", ExitCode.STALE_PROJECT_RECORD, d)


class ConversionConflictError(VersionManagerError):
    def __init__(self, message: str, details: dict = None):
        d = details or {}
        if "suggestion" not in d:
            d["suggestion"] = "use --force to overwrite conflicting configuration"
        super().__init__(message, ExitCode.CONVERSION_CONFLICT, d)


class RecursionError(VersionManagerError):
    def __init__(self, command: str, details: dict = None):
        super().__init__(f"infinite recursion detected while dispatching '{command}'", ExitCode.RECURSION_DETECTED, details)
