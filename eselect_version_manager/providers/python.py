"""Select slotted Gentoo Python interpreters, leaving python-exec defaults intact."""

import os
from typing import List

from .base import BaseProvider
from ..models import InstalledPackage
from ..errors import MissingExecutableError


class PythonProvider(BaseProvider):
    """Map python/python3 shims to package-owned versioned Python binaries."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def package_atom(self) -> str:
        return "dev-lang/python"

    @property
    def commands(self) -> List[str]:
        return ["python", "python3"]

    def find_executable(self, package: InstalledPackage, command: str) -> str:
        if command not in self.commands:
            return super().find_executable(package, command)

        # Gentoo uses SLOT=3.13, 3.14, etc. Each interpreter is versioned.
        versioned_name = "python" + package.slot
        for path in package.contents:
            if os.path.basename(path) != versioned_name:
                continue
            if (
                self.validate_executable(package, command, path)
                and os.path.isfile(path)
                and os.access(path, os.X_OK)
            ):
                return path

        raise MissingExecutableError(
            tool=self.name,
            command=command,
            pkg=package.cpv,
            expected_path="/usr/bin/" + versioned_name,
            details={
                "reason": "selected Python package lacks a package-owned "
                          "executable versioned interpreter in Portage CONTENTS",
            },
        )
