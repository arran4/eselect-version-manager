"""Unslotted fixture provider demonstrating handling of unslotted packages."""

import os
from typing import Dict, List
from .base import BaseProvider
from ..models import InstalledPackage


class UnslottedFixtureProvider(BaseProvider):
    """Test fixture provider for unslotted package app-misc/unslotted-fixture."""

    @property
    def name(self) -> str:
        return "unslotted"

    @property
    def package_atom(self) -> str:
        return "app-misc/unslotted-fixture"

    @property
    def commands(self) -> List[str]:
        return ["unslotted-tool"]

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        return {
            "VM_UNSLOTTED_ACTIVE": "1",
            "VM_UNSLOTTED_VERSION": package.version,
        }
