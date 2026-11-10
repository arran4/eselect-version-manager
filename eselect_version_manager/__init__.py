"""Gentoo-native project-aware toolchain version manager."""

__version__ = "0.1.0"
__author__ = "arran4"

from .errors import VersionManagerError, ExitCode
from .models import Scope, ResolutionResult, InstalledPackage
from .resolver import Resolver
from .conversion import convert_to_file, convert_to_user

__all__ = [
    "__version__",
    "VersionManagerError",
    "ExitCode",
    "Scope",
    "ResolutionResult",
    "InstalledPackage",
    "Resolver",
    "convert_to_file",
    "convert_to_user",
]
