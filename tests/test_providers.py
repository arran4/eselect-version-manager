"""Unit tests for providers and native version file detection."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.providers.registry import (
    get_default_registry,
    create_default_registry,
    ProviderRegistry,
)
from eselect_version_manager.providers.base import GenericProvider
from eselect_version_manager.providers.go import GoProvider
from eselect_version_manager.providers.fixture import FixtureProvider
from eselect_version_manager.models import InstalledPackage
from eselect_version_manager.errors import (
    UnknownToolError,
    VersionManagerError,
    NoMatchingVersionError,
    MissingExecutableError,
    ExitCode,
)


def test_provider_registry():
    registry = get_default_registry()
    assert "go" in registry.list_tools()
    assert "fixture" in registry.list_tools()

    p_go = registry.get_provider("go")
    assert p_go.package_atom == "dev-lang/go"

    # Command mapping
    assert registry.get_provider("gofmt").name == "go"
    assert registry.get_provider("fixture-tool").name == "fixture"
    assert registry.get_provider("fixture-helper").name == "fixture"

    with pytest.raises(UnknownToolError):
        registry.get_provider("nonexistent-tool")


def test_go_native_from_file_gomod(tmp_path):
    provider = GoProvider()
    gomod = tmp_path / "go.mod"
    gomod.write_text("module example.com/test\n\ngo 1.22\n")

    constraint = provider.parse_native_version_file(str(tmp_path))
    assert constraint == ">=1.22"


def test_go_native_from_file_toolchain_directive(tmp_path):
    provider = GoProvider()
    gomod = tmp_path / "go.mod"
    gomod.write_text("module example.com/test\n\ngo 1.21\n\ntoolchain go1.22.4\n")

    constraint = provider.parse_native_version_file(str(tmp_path))
    assert constraint == "1.22.4"


def test_go_native_from_file_gowork_priority(tmp_path):
    provider = GoProvider()
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.20\n")
    (tmp_path / "go.work").write_text("go 1.23.0\n\ntoolchain go1.23.2\n")

    constraint = provider.parse_native_version_file(str(tmp_path))
    assert constraint == "1.23.2"


def test_go_native_missing_files_error(tmp_path):
    provider = GoProvider()
    with pytest.raises(VersionManagerError) as exc_info:
        provider.parse_native_version_file(str(tmp_path))
    assert exc_info.value.exit_code == ExitCode.UNSUPPORTED_VERSION_FILE


def test_go_environment_sets_gotoolchain_local():
    provider = GoProvider()
    pkg = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=["/usr/lib/go/1.22/bin/go"],
    )
    env = provider.get_environment(pkg, "/usr/lib/go/1.22/bin/go")
    assert env["GOTOOLCHAIN"] == "local"
    assert env.get("GOROOT") == "/usr/lib/go/1.22"


def test_fixture_environment():
    provider = FixtureProvider()
    pkg = InstalledPackage(
        cpv="app-misc/version-manager-fixture-2.0",
        category="app-misc",
        pkg_name="version-manager-fixture",
        version="2.0",
        revision="r0",
        slot="2",
        subslot="",
        contents=[],
    )
    env = provider.get_environment(pkg, "/usr/lib/vm-fixture-2/bin/fixture-tool")
    assert env["VM_FIXTURE_HOME"] == "/usr/lib/vm-fixture-2"
    assert env["VM_FIXTURE_SLOT"] == "2"


def test_go_from_file_minimum_version_satisfied_by_newer_installed(tmp_path):
    provider = GoProvider()
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.20\n")

    # Only newer versions 1.22.4 and 1.23.1 installed (no 1.20 installed)
    installed = [
        InstalledPackage("dev-lang/go-1.22.4", "dev-lang", "go", "1.22.4", "r0", "1.22", "", ["/usr/bin/go-1.22"]),
        InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
    ]

    best_pkg, desc = provider.resolve_native_package(str(tmp_path), installed)
    assert best_pkg.version == "1.23.1"
    assert ">=1.20" in desc


def test_go_from_file_preferred_toolchain(tmp_path):
    provider = GoProvider()
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.20\n\ntoolchain go1.22.4\n")

    # Both 1.22.4 and 1.23.1 installed; preferred 1.22.4 should be selected!
    installed = [
        InstalledPackage("dev-lang/go-1.22.4", "dev-lang", "go", "1.22.4", "r0", "1.22", "", ["/usr/bin/go-1.22"]),
        InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
    ]

    best_pkg, desc = provider.resolve_native_package(str(tmp_path), installed)
    assert best_pkg.version == "1.22.4"
    assert "toolchain 1.22.4" in desc


def test_go_from_file_preferred_toolchain_newer_fallback(tmp_path):
    provider = GoProvider()
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.20\n\ntoolchain go1.22.4\n")

    # Only 1.23.1 installed; toolchain 1.22.4 not installed -> fall back to >=1.22.4
    installed = [
        InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
    ]

    best_pkg, desc = provider.resolve_native_package(str(tmp_path), installed)
    assert best_pkg.version == "1.23.1"
    assert ">=1.22.4" in desc


def test_go_from_file_missing_compatible_toolchain_fails(tmp_path):
    provider = GoProvider()
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.25\n")

    # Installed versions are 1.22.4 and 1.23.1; neither satisfies >=1.25
    installed = [
        InstalledPackage("dev-lang/go-1.22.4", "dev-lang", "go", "1.22.4", "r0", "1.22", "", ["/usr/bin/go-1.22"]),
        InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
    ]

    with pytest.raises(NoMatchingVersionError) as exc_info:
        provider.resolve_native_package(str(tmp_path), installed)
    assert "no installed version satisfies the requested constraint" in str(exc_info.value)
    assert "no installed dev-lang/go package satisfies minimum version requirement" in exc_info.value.details.get("reason", "")


def test_go_from_file_nested_module_and_workspace(tmp_path):
    provider = GoProvider()

    # Create root workspace
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "go.work").write_text("go 1.23\n\ntoolchain go1.23.1\n")

    # Create sub-module
    sub_mod = workspace_dir / "submodule"
    sub_mod.mkdir()
    (sub_mod / "go.mod").write_text("module example.com/sub\n\ngo 1.21\n")

    installed = [
        InstalledPackage("dev-lang/go-1.21.5", "dev-lang", "go", "1.21.5", "r0", "1.21", "", ["/usr/bin/go-1.21"]),
        InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
    ]

    # Inside sub_mod, go.work in parent directory takes precedence!
    best_pkg, desc = provider.resolve_native_package(str(sub_mod), installed)
    assert best_pkg.version == "1.23.1"
    assert "toolchain 1.23.1" in desc
    assert "go.work" in desc


def test_find_executable_rejects_conflicting_unowned_binary(tmp_path):
    """
    Test that resolving Package B never executes Package A's conflicting binary,
    and raises MissingExecutableError if Package B's executable is missing.
    """
    provider = GoProvider()

    # Package B (go-1.22.4) owns /usr/lib/go-1.22/bin/go
    pkg_b = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=["/usr/lib/go-1.22/bin/go"],
    )

    # Candidate belonging to Package B is resolved
    exec_path = provider.find_executable(pkg_b, "go")
    assert exec_path == "/usr/lib/go-1.22/bin/go"

    # Conflicting package where CONTENTS does not contain the binary
    pkg_empty = InstalledPackage(
        cpv="dev-lang/go-1.99",
        category="dev-lang",
        pkg_name="go",
        version="1.99",
        revision="r0",
        slot="1.99",
        subslot="",
        contents=[],
    )

    # Must raise MissingExecutableError rather than executing conflicting /usr/bin/go
    with pytest.raises(MissingExecutableError):
        provider.find_executable(pkg_empty, "go")


def test_dynamic_provider_from_directory(tmp_path, monkeypatch):
    """Test dynamic provider loading from providers.d directory."""
    providers_dir = tmp_path / "providers.d"
    providers_dir.mkdir()

    # Define a custom provider for python
    (providers_dir / "python.conf").write_text(
        'PACKAGE_ATOM="dev-lang/python"\n'
        'COMMANDS="python python3"\n'
    )

    registry = ProviderRegistry()
    registry.load_providers_from_directory(str(providers_dir))

    p = registry.get_provider("python")
    assert p.name == "python"
    assert p.package_atom == "dev-lang/python"
    assert p.commands == ["python", "python3"]

    # Command mapping
    assert registry.find_provider_for_command("python3").name == "python"
