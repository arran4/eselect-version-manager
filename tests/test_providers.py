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
from eselect_version_manager.providers.go import GoProvider, find_go_native_file
from eselect_version_manager.providers.fixture import FixtureProvider
from eselect_version_manager.models import InstalledPackage
from eselect_version_manager.errors import (
    UnknownToolError,
    VersionManagerError,
    NoMatchingVersionError,
    MissingExecutableError,
    InvalidConfigError,
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

    bin_b = tmp_path / "lib" / "go-1.22" / "bin" / "go"
    bin_b.parent.mkdir(parents=True, exist_ok=True)
    bin_b.write_text("#!/bin/sh\necho go1.22\n")
    bin_b.chmod(0o755)

    # Package B (go-1.22.4) owns bin_b
    pkg_b = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=[str(bin_b)],
    )

    # Candidate belonging to Package B is resolved
    exec_path = provider.find_executable(pkg_b, "go")
    assert exec_path == str(bin_b)

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


def test_executable_ownership_foreign_missing_replaced_versioned(tmp_path):
    """
    Test that BaseProvider / GoProvider strictly enforce Portage CONTENTS metadata:
    - foreign binary (not in CONTENTS) is rejected even if slot/version substring matches.
    - missing binary (in CONTENTS but not on disk) is rejected.
    - replaced binary (in CONTENTS but not executable or replaced by directory) is rejected.
    - valid versioned binary (in CONTENTS, exists, executable) is accepted.
    """
    provider = GoProvider()

    # 1. Foreign binary exists and is executable, but is not in package.contents
    foreign_dir = tmp_path / "foreign"
    foreign_dir.mkdir(parents=True, exist_ok=True)
    foreign_bin = foreign_dir / "go-1.22"
    foreign_bin.write_text("#!/bin/sh\nexit 0\n")
    foreign_bin.chmod(0o755)

    pkg_foreign = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=["/unrelated/file/path"],
    )
    # validate_executable must return False for foreign binary despite '1.22' substring!
    assert not provider.validate_executable(pkg_foreign, "go", str(foreign_bin))

    # 2. Missing binary: listed in contents, but does NOT exist on disk
    missing_path = str(tmp_path / "nonexistent" / "bin" / "go")
    pkg_missing = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=[missing_path],
    )
    with pytest.raises(MissingExecutableError):
        provider.find_executable(pkg_missing, "go")

    # 3. Replaced binary: in contents and on disk, but NOT executable (mode 0644)
    non_exec = tmp_path / "replaced" / "go"
    non_exec.parent.mkdir(parents=True, exist_ok=True)
    non_exec.write_text("not a script")
    non_exec.chmod(0o644)

    pkg_replaced = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=[str(non_exec)],
    )
    with pytest.raises(MissingExecutableError):
        provider.find_executable(pkg_replaced, "go")

    # 4. Valid versioned binary: in contents, exists on disk, executable
    valid_bin = tmp_path / "valid" / "bin" / "go-1.22"
    valid_bin.parent.mkdir(parents=True, exist_ok=True)
    valid_bin.write_text("#!/bin/sh\nexit 0\n")
    valid_bin.chmod(0o755)

    pkg_valid = InstalledPackage(
        cpv="dev-lang/go-1.22.4",
        category="dev-lang",
        pkg_name="go",
        version="1.22.4",
        revision="r0",
        slot="1.22",
        subslot="",
        contents=[str(valid_bin)],
    )
    assert provider.find_executable(pkg_valid, "go") == str(valid_bin)


def test_go_toolchain_preference_unsatisfied_fails(tmp_path):
    """
    When 'toolchain' specifies go1.24.0 but only 1.22.4 is installed (which satisfies go 1.20),
    resolution must fail with NoMatchingVersionError detailing that toolchain requirement
    is unsatisfied.
    """
    mod_dir = tmp_path / "mod_toolchain"
    mod_dir.mkdir()
    (mod_dir / "go.mod").write_text("module example.com/test\ngo 1.20\ntoolchain go1.24.0\n")

    provider = GoProvider()
    installed = [
        InstalledPackage("dev-lang/go-1.22.4", "dev-lang", "go", "1.22.4", "r0", "1.22", "", ["/bin/go"]),
    ]

    with pytest.raises(NoMatchingVersionError) as exc_info:
        provider.resolve_native_package(str(mod_dir), installed)

    diag = exc_info.value.format_diagnostic()
    assert "1.24.0" in diag
    assert "toolchain" in diag


def test_gowork_environment_handling(tmp_path, monkeypatch):
    """
    Test GOWORK environment variable handling:
    - GOWORK=off ignores go.work and uses go.mod
    - GOWORK=custom_path uses that file
    - Missing GOWORK path raises VersionManagerError
    """
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "go.work").write_text("go 1.22\ntoolchain go1.22.4\n")

    sub_dir = ws_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "go.mod").write_text("module example.com/sub\ngo 1.21\n")

    custom_work = tmp_dir = tmp_path / "custom.work"
    custom_work.write_text("go 1.23\ntoolchain go1.23.1\n")

    # 1. Normal upward search finds go.work
    monkeypatch.delenv("GOWORK", raising=False)
    file_type, path = find_go_native_file(str(sub_dir))
    assert file_type == "go.work"
    assert path == str(ws_dir / "go.work")

    # 2. GOWORK=off ignores go.work and finds go.mod
    monkeypatch.setenv("GOWORK", "off")
    file_type, path = find_go_native_file(str(sub_dir))
    assert file_type == "go.mod"
    assert path == str(sub_dir / "go.mod")

    # 3. Custom GOWORK path
    monkeypatch.setenv("GOWORK", str(custom_work))
    file_type, path = find_go_native_file(str(sub_dir))
    assert file_type == "go.work"
    assert path == str(custom_work)

    # 4. Nonexistent GOWORK path raises VersionManagerError
    monkeypatch.setenv("GOWORK", "/nonexistent/go.work")
    with pytest.raises(VersionManagerError):
        find_go_native_file(str(sub_dir))


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


def test_dynamic_provider_error_reporting_and_precedence(tmp_path):
    """
    Test that malformed provider files report actionable errors with filename,
    user providers take precedence over system, and built-ins cannot be overridden
    without OVERRIDE_BUILTIN=true.
    """
    sys_dir = tmp_path / "sys_providers"
    user_dir = tmp_path / "user_providers"
    sys_dir.mkdir()
    user_dir.mkdir()

    # 1. Malformed syntax reports error with filename
    bad_conf = sys_dir / "bad.conf"
    bad_conf.write_text("INVALID SYNTAX WITHOUT EQUALS\n")

    registry = ProviderRegistry()
    with pytest.raises(InvalidConfigError) as exc_info:
        registry.load_providers_from_directory(str(sys_dir))
    assert str(bad_conf) in str(exc_info.value)
    bad_conf.unlink()

    # 2. Missing PACKAGE_ATOM reports error with filename
    missing_atom = sys_dir / "missing.conf"
    missing_atom.write_text("COMMANDS=\"cmd1\"\n")
    with pytest.raises(InvalidConfigError) as exc_info:
        registry.load_providers_from_directory(str(sys_dir))
    assert str(missing_atom) in str(exc_info.value)
    missing_atom.unlink()

    # 3. Accidental override of built-in is blocked
    go_override = sys_dir / "go.conf"
    go_override.write_text('PACKAGE_ATOM="dev-lang/go-bin"\n')
    registry = ProviderRegistry()
    registry.register(GoProvider(), is_builtin=True)
    with pytest.raises(InvalidConfigError) as exc_info:
        registry.load_providers_from_directory(str(sys_dir))
    assert "attempts to override built-in provider 'go'" in str(exc_info.value)

    # 4. Intentional override with OVERRIDE_BUILTIN="true" succeeds
    go_override.write_text('PACKAGE_ATOM="dev-lang/go-bin"\nOVERRIDE_BUILTIN="true"\n')
    registry.load_providers_from_directory(str(sys_dir))
    assert registry.get_provider("go").package_atom == "dev-lang/go-bin"
    go_override.unlink()

    # 5. User provider takes precedence over system provider
    (sys_dir / "rust.conf").write_text('PACKAGE_ATOM="dev-lang/rust"\n')
    (user_dir / "rust.conf").write_text('PACKAGE_ATOM="dev-lang/rust-bin"\n')
    reg = ProviderRegistry()
    reg.load_providers_from_directory(str(sys_dir), is_user=False)
    assert reg.get_provider("rust").package_atom == "dev-lang/rust"
    reg.load_providers_from_directory(str(user_dir), is_user=True)
    assert reg.get_provider("rust").package_atom == "dev-lang/rust-bin"
