"""Unit tests for providers and native version file detection."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.providers.registry import get_default_registry
from eselect_version_manager.providers.go import GoProvider
from eselect_version_manager.providers.fixture import FixtureProvider
from eselect_version_manager.models import InstalledPackage
from eselect_version_manager.errors import UnknownToolError, VersionManagerError, ExitCode


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
    assert constraint == "1.22"


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
