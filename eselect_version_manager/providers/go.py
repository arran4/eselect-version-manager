"""Go toolchain provider for dev-lang/go."""

import os
import re
from typing import Dict, List, Optional, Tuple
from .base import BaseProvider
from ..models import InstalledPackage
from ..errors import VersionManagerError, ExitCode


def find_go_native_file(start_dir: str) -> Tuple[str, str]:
    """
    Find applicable Go native configuration file with workspace precedence.
    Ascends from start_dir checking for go.work, then go.mod.
    Honours GOWORK environment variable:
      - 'off': workspace mode disabled, ignore go.work and search for go.mod
      - custom path: use specified go.work file if it exists
      - unset/empty/auto: search upwards from start_dir for go.work, then go.mod
    Returns (file_type, file_path) where file_type is 'go.work' or 'go.mod'.
    """
    canonical_start = os.path.realpath(os.path.abspath(start_dir))
    gowork_env = os.environ.get("GOWORK", "").strip()

    # 1. Search for go.work unless GOWORK=off
    if gowork_env == "off":
        pass  # Workspace mode disabled
    elif gowork_env and gowork_env != "auto":
        gowork_path = os.path.realpath(
            gowork_env if os.path.isabs(gowork_env) else os.path.join(canonical_start, gowork_env)
        )
        if os.path.isfile(gowork_path):
            return ("go.work", gowork_path)
        raise VersionManagerError(
            f"GOWORK is set to '{gowork_env}' but file '{gowork_path}' does not exist",
            exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
            details={"GOWORK": gowork_env, "resolved_path": gowork_path}
        )
    else:
        # Search upwards for go.work (workspace mode has highest precedence)
        curr = canonical_start
        visited = set()
        while curr and curr not in visited:
            visited.add(curr)
            gowork = os.path.join(curr, "go.work")
            if os.path.isfile(gowork):
                return ("go.work", gowork)
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

    # 2. Search upwards for go.mod (nearest module)
    curr = canonical_start
    visited = set()
    while curr and curr not in visited:
        visited.add(curr)
        gomod = os.path.join(curr, "go.mod")
        if os.path.isfile(gomod):
            return ("go.mod", gomod)
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    raise VersionManagerError(
        f"cannot resolve go from-file: neither 'go.work' nor 'go.mod' found in '{start_dir}' or any parent directory",
        exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
        details={
            "start_dir": start_dir,
            "suggestion": "create a go.mod or specify explicit version in .eselect.conf"
        }
    )


def parse_go_directives(target_file: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse (minimum_go_ver, preferred_toolchain_ver) from go.work or go.mod."""
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

    if not go_ver and not toolchain_ver:
        raise VersionManagerError(
            f"no 'go' or 'toolchain' directive found in '{target_file}'",
            exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
            details={"file": target_file}
        )

    return (go_ver, toolchain_ver)


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

    def parse_native_version_file(self, project_root: str) -> str:
        """
        Parse Go native requirements from go.work or go.mod.
        Understands workspace priority over module, and toolchain directive over go directive.
        Treats 'go' directive as minimum required version (>=), not an exact pin.
        """
        _, target_file = find_go_native_file(project_root)
        go_ver, toolchain_ver = parse_go_directives(target_file)
        if toolchain_ver:
            return toolchain_ver
        return f">={go_ver}"

    def resolve_native_package(
        self,
        start_dir: str,
        installed_packages: List[InstalledPackage]
    ) -> Tuple[InstalledPackage, str]:
        """
        Resolve best installed package satisfying native Go directives.
        Prefers exact toolchain directive if installed; otherwise satisfies minimum requirement.
        """
        from ..portage_backend import match_packages

        file_type, target_file = find_go_native_file(start_dir)
        go_ver, toolchain_ver = parse_go_directives(target_file)

        # 1. If toolchain directive is specified, it represents the preferred toolchain
        if toolchain_ver:
            exact_matches = match_packages(installed_packages, self.package_atom, toolchain_ver)
            if exact_matches:
                return (exact_matches[-1], f"toolchain {toolchain_ver} ({file_type})")

            # Fall back to newer installed toolchain satisfying >= toolchain_ver
            range_matches = match_packages(installed_packages, self.package_atom, f">={toolchain_ver}")
            if range_matches:
                return (range_matches[-1], f">={toolchain_ver} ({file_type})")

            # In Go semantics with GOTOOLCHAIN=local, the selected toolchain must satisfy >= toolchain_ver.
            # If no installed toolchain meets toolchain_ver, resolution must fail even if go_ver minimum is met.
            installed_strs = [f"{p.version} (slot {p.slot})" for p in installed_packages]
            from ..errors import NoMatchingVersionError
            raise NoMatchingVersionError(
                tool=self.name,
                requested=f"toolchain {toolchain_ver} (go {go_ver}) from {target_file}",
                provider=self.package_atom,
                installed=installed_strs,
                details={
                    "source": target_file,
                    "reason": (
                        f"no installed {self.package_atom} package satisfies preferred toolchain '{toolchain_ver}' "
                        f"or newer (required by 'toolchain' directive in {target_file}, despite installed packages satisfying 'go {go_ver}')"
                    )
                }
            )

        # 2. 'go' directive represents minimum required version
        if go_ver:
            matches = match_packages(installed_packages, self.package_atom, f">={go_ver}")
            if matches:
                return (matches[-1], f">={go_ver} ({file_type})")

        # No compatible toolchain found
        req_desc = f"toolchain {toolchain_ver}" if toolchain_ver else f"go >={go_ver}"
        installed_strs = [f"{p.version} (slot {p.slot})" for p in installed_packages]
        from ..errors import NoMatchingVersionError
        raise NoMatchingVersionError(
            tool=self.name,
            requested=f"{req_desc} from {target_file}",
            provider=self.package_atom,
            installed=installed_strs,
            details={
                "source": target_file,
                "reason": f"no installed {self.package_atom} package satisfies minimum version requirement"
            }
        )

    def validate_executable(self, package: InstalledPackage, command: str, candidate_path: str) -> bool:
        return super().validate_executable(package, command, candidate_path)

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        env = {
            # Enforce Portage management: disable automatic network downloads
            "GOTOOLCHAIN": "local",
        }

        parent_bin = os.path.dirname(executable_path)
        if os.path.basename(parent_bin) == "bin":
            potential_goroot = os.path.dirname(parent_bin)
            if "go" in potential_goroot.lower():
                env["GOROOT"] = potential_goroot

        return env
