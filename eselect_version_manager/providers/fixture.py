"""Controlled test fixture provider demonstrating multi-executable and slotted co-installable toolchains."""

import os
from typing import Dict, List
from .base import BaseProvider
from ..models import InstalledPackage
from ..errors import MissingExecutableError


class FixtureProvider(BaseProvider):
    """Test fixture provider for app-misc/version-manager-fixture."""

    @property
    def name(self) -> str:
        return "fixture"

    @property
    def package_atom(self) -> str:
        return "app-misc/version-manager-fixture"

    @property
    def commands(self) -> List[str]:
        return ["fixture-tool", "fixture-helper"]

    def find_executable(self, package: InstalledPackage, command: str) -> str:
        # Check slotted lib directories first
        slot_lib_path = f"/usr/lib/vm-fixture-{package.slot}/bin/{command}"
        if os.path.exists(slot_lib_path) and os.access(slot_lib_path, os.X_OK):
            return slot_lib_path

        # Check versioned bin symlink / executable in /usr/bin
        versioned_bin = f"/usr/bin/{command}-{package.slot}"
        if os.path.exists(versioned_bin) and os.access(versioned_bin, os.X_OK):
            return versioned_bin

        # Check package contents
        for path in package.contents:
            if os.path.basename(path) in (command, f"{command}-{package.slot}"):
                if os.path.exists(path) and os.access(path, os.X_OK):
                    return path

        return super().find_executable(package, command)

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        return {
            "VM_FIXTURE_HOME": f"/usr/lib/vm-fixture-{package.slot}",
            "VM_FIXTURE_SLOT": package.slot,
            "VM_FIXTURE_VERSION": package.version,
        }
