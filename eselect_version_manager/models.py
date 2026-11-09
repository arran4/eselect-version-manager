"""Data structures and models for eselect-version-manager."""

import dataclasses
import enum
from typing import Dict, List, Optional


class Scope(enum.Enum):
    INVOCATION_OVERRIDE = "invocation_override"
    USER_PROJECT = "user_project"
    PROJECT_FILE = "project_file"
    PARENT_PROJECT = "parent_project"
    USER_DEFAULT = "user_default"
    SYSTEM_DEFAULT = "system_default"
    SYSTEM_FALLBACK = "system_fallback"

    def display_name(self) -> str:
        names = {
            Scope.INVOCATION_OVERRIDE: "Command Override",
            Scope.USER_PROJECT: "Private User Project Override",
            Scope.PROJECT_FILE: ".eselect.conf",
            Scope.PARENT_PROJECT: "Parent Project",
            Scope.USER_DEFAULT: "User Default",
            Scope.SYSTEM_DEFAULT: "System Default",
            Scope.SYSTEM_FALLBACK: "System Executable",
        }
        return names.get(self, self.value)


@dataclasses.dataclass
class ToolSelection:
    """A configured selection for a tool."""
    tool: str
    raw_value: str
    scope: Scope
    source_file: Optional[str] = None
    project_root: Optional[str] = None


@dataclasses.dataclass
class InstalledPackage:
    """Metadata for an installed Portage package."""
    cpv: str                    # e.g. "dev-lang/go-1.22.4"
    category: str               # "dev-lang"
    pkg_name: str               # "go"
    version: str                # "1.22.4"
    revision: str               # "r0"
    slot: str                   # "1.22" or "0"
    subslot: str                # "" or "0"
    contents: List[str]         # Installed file absolute paths


@dataclasses.dataclass
class ResolutionStep:
    """Diagnostic step in precedence chain."""
    scope: Scope
    source_location: str
    tool: str
    raw_value: Optional[str] = None
    matched: bool = False
    details: Optional[str] = None


@dataclasses.dataclass
class ResolutionResult:
    """Outcome of resolving a tool to an installed package and executable."""
    tool: str
    command: str
    requested_constraint: str
    selected_scope: Scope
    source_file: Optional[str]
    project_root: Optional[str]
    provider_name: str
    provider_atom: str
    package: Optional[InstalledPackage]
    executable_path: str
    env_vars: Dict[str, str] = dataclasses.field(default_factory=dict)
    steps: List[ResolutionStep] = dataclasses.field(default_factory=list)
    is_system_fallback: bool = False
