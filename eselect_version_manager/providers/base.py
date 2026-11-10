"""Provider base class and types."""

import abc
import os
from typing import Dict, List, Optional
from ..models import InstalledPackage
from ..errors import MissingExecutableError, VersionManagerError


class BaseProvider(abc.ABC):
    """Base class for toolchain providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the tool, e.g. 'go'."""
        pass

    @property
    @abc.abstractmethod
    def package_atom(self) -> str:
        """Primary Gentoo package atom, e.g. 'dev-lang/go'."""
        pass

    @property
    @abc.abstractmethod
    def commands(self) -> List[str]:
        """List of executable commands exposed by this provider, e.g. ['go', 'gofmt']."""
        pass

    @property
    def supports_native_file(self) -> bool:
        """Whether this provider supports reading requirements from native project files."""
        return False

    def parse_native_version_file(self, project_root: str) -> Optional[str]:
        """
        Parse native project files (e.g. go.mod / go.work) and return a version constraint.
        Raise VersionManagerError if required file is missing or corrupted.
        """
        return None

    def validate_executable(self, package: InstalledPackage, command: str, candidate_path: str) -> bool:
        """
        Validate that candidate_path actually belongs to the selected package.
        Prevents executing an executable belonging to a conflicting version.
        Uses Portage installed-file metadata (package.contents).
        """
        if not package.contents:
            return False

        cand_abs = os.path.abspath(candidate_path)
        canonical_cand = os.path.realpath(candidate_path) if os.path.exists(candidate_path) else None

        for path in package.contents:
            entry_abs = os.path.abspath(path)
            if cand_abs == entry_abs:
                return True
            if canonical_cand and os.path.exists(entry_abs):
                if os.path.realpath(entry_abs) == canonical_cand:
                    return True

        return False

    def find_executable(self, package: InstalledPackage, command: str) -> str:
        """
        Locate the absolute path to command for the given installed package.
        Guarantees that the resolved executable belongs to the selected package.
        Never falls back to conflicting system executables in /usr/bin.
        Never returns a nonexistent or non-executable binary.
        """
        # 1. First search package CONTENTS
        if package.contents:
            for path in package.contents:
                base = os.path.basename(path)
                # Exact command match, slotted match, or versioned match
                is_match = (
                    base == command
                    or base == f"{command}-{package.slot}"
                    or base == f"{command}{package.slot}"
                    or base == f"{command}-{package.version}"
                )
                if is_match and ("/bin" in path or path.endswith(f"/{command}")):
                    if self.validate_executable(package, command, path):
                        if os.path.isfile(path) and os.access(path, os.X_OK):
                            return path

        # 2. Check slotted/versioned installation paths
        versioned_locations = [
            f"/usr/lib/{package.pkg_name}/{package.slot}/bin/{command}",
            f"/usr/lib/{package.pkg_name}-{package.slot}/bin/{command}",
            f"/usr/bin/{command}-{package.slot}",
            f"/usr/bin/{command}-{package.version}",
        ]
        for loc in versioned_locations:
            if os.path.isfile(loc) and os.access(loc, os.X_OK):
                if self.validate_executable(package, command, loc):
                    return loc

        # 3. Check /usr/bin/{command} ONLY if validated to belong to this package
        unversioned = f"/usr/bin/{command}"
        if os.path.isfile(unversioned) and os.access(unversioned, os.X_OK):
            if self.validate_executable(package, command, unversioned):
                return unversioned

        expected = versioned_locations[0] if versioned_locations else f"/usr/bin/{command}"
        raise MissingExecutableError(
            tool=self.name,
            command=command,
            pkg=package.cpv,
            expected_path=expected,
            details={
                "reason": f"no executable for command '{command}' belonging to package '{package.cpv}' could be found or validated",
                "searched_paths": ", ".join(versioned_locations + [unversioned]),
            }
        )

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        """Return environment variable updates required by this toolchain."""
        return {}


class GenericProvider(BaseProvider):
    """Generic Portage provider for any installed package atom."""

    def __init__(self, name: str, package_atom: str, commands: Optional[List[str]] = None):
        self._name = name
        self._package_atom = package_atom
        self._commands = commands if commands else [name]

    @property
    def name(self) -> str:
        return self._name

    @property
    def package_atom(self) -> str:
        return self._package_atom

    @property
    def commands(self) -> List[str]:
        return self._commands
