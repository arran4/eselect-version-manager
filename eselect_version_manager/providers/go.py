"""Go toolchain provider for dev-lang/go."""

import os
import re
from typing import Dict, List, Optional
from .base import BaseProvider
from ..models import InstalledPackage
from ..errors import VersionManagerError, ExitCode


class GoProvider(BaseProvider):
    """Provider adapter for Go (dev-lang/go)."""

    @property
    def name(self) -> str:
        return "go"

    @property
    def package_atom(self) -> str:
        return "dev-lang/go"

    @property
    def commands(self) -> List[str]:
        return ["go", "gofmt"]

    @property
    def supports_native_file(self) -> bool:
        return True

    def parse_native_version_file(self, project_root: str) -> Optional[str]:
        """
        Parse Go native requirements from go.work or go.mod.
        Understands workspace priority over module, and toolchain directive over go directive.
        Treats 'go' directive as minimum required version (>=), not an exact pin.
        """
        gowork_path = os.path.join(project_root, "go.work")
        gomod_path = os.path.join(project_root, "go.mod")

        target_file = None
        if os.path.isfile(gowork_path):
            target_file = gowork_path
        elif os.path.isfile(gomod_path):
            target_file = gomod_path
        else:
            raise VersionManagerError(
                f"cannot resolve go from-file: neither 'go.work' nor 'go.mod' found in '{project_root}'",
                exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
                details={
                    "project_root": project_root,
                    "checked_files": f"{gowork_path}, {gomod_path}",
                    "suggestion": "create a go.mod or specify explicit version in .eselect.conf"
                }
            )

        go_ver = None
        toolchain_ver = None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("toolchain "):
                        # e.g. "toolchain go1.22.4"
                        parts = stripped.split()
                        if len(parts) >= 2:
                            val = parts[1]
                            if val.startswith("go"):
                                toolchain_ver = val[2:]
                            else:
                                toolchain_ver = val
                    elif stripped.startswith("go "):
                        # e.g. "go 1.22" or "go 1.22.0"
                        parts = stripped.split()
                        if len(parts) >= 2:
                            go_ver = parts[1]
        except OSError as e:
            raise VersionManagerError(
                f"failed to read {target_file}: {e}",
                exit_code=ExitCode.GENERAL_ERROR,
                details={"file": target_file}
            )

        # Toolchain directive takes precedence if specified
        if toolchain_ver:
            return toolchain_ver

        # Otherwise go directive specifies minimum required language series
        # (e.g. '1.22' matches Go 1.22 series, allowing patch updates without being an exact pin)
        if go_ver:
            return go_ver

        raise VersionManagerError(
            f"no 'go' or 'toolchain' directive found in '{target_file}'",
            exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
            details={"file": target_file}
        )

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        env = {
            # Enforce Portage management: disable automatic network downloads
            "GOTOOLCHAIN": "local",
        }

        # Detect GOROOT if installed in /usr/lib/go...
        # If executable is e.g. /usr/lib/go/1.22/bin/go -> GOROOT is /usr/lib/go/1.22
        parent_bin = os.path.dirname(executable_path)
        if os.path.basename(parent_bin) == "bin":
            potential_goroot = os.path.dirname(parent_bin)
            if "go" in potential_goroot.lower():
                env["GOROOT"] = potential_goroot

        return env
