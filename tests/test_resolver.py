"""Unit tests for precedence resolution and explanation engine."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.models import Scope, InstalledPackage
from eselect_version_manager.resolver import Resolver
from eselect_version_manager.project import (
    canonicalize_path,
    save_private_project_config,
)
from eselect_version_manager.config import update_config_file, get_system_config_path
from eselect_version_manager.errors import NoMatchingVersionError, RecursionError


def fake_installed_packages(atom, eroot=None):
    if atom == "dev-lang/go":
        return [
            InstalledPackage("dev-lang/go-1.21.5", "dev-lang", "go", "1.21.5", "r0", "1.21", "", ["/usr/bin/go-1.21"]),
            InstalledPackage("dev-lang/go-1.22.4", "dev-lang", "go", "1.22.4", "r0", "1.22", "", ["/usr/bin/go-1.22"]),
            InstalledPackage("dev-lang/go-1.23.1", "dev-lang", "go", "1.23.1", "r0", "1.23", "", ["/usr/bin/go-1.23"]),
        ]
    elif atom == "app-misc/version-manager-fixture":
        return [
            InstalledPackage("app-misc/version-manager-fixture-1.0", "app-misc", "version-manager-fixture", "1.0", "r0", "1", "", ["/usr/bin/fixture-tool-1"]),
            InstalledPackage("app-misc/version-manager-fixture-2.0", "app-misc", "version-manager-fixture", "2.0", "r0", "2", "", ["/usr/bin/fixture-tool-2"]),
        ]
    return []


import eselect_version_manager.resolver as resolver_mod
resolver_mod.get_installed_packages = fake_installed_packages
resolver_mod.find_system_executable = lambda cmd: f"/usr/bin/{cmd}"


def test_nearest_project_private_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    canon_root = canonicalize_path(str(proj_dir))

    # .eselect.conf specifies 1.21
    (proj_dir / ".eselect.conf").write_text('VM_GO="1.21"\n')

    # Private config specifies 1.22
    save_private_project_config(canon_root, {"VM_GO": "1.22"})

    resolver = Resolver()
    res = resolver.resolve("go", current_dir=str(proj_dir))

    assert res.selected_scope == Scope.USER_PROJECT
    assert res.package.version == "1.22.4"
    assert res.package.slot == "1.22"


def test_parent_project_inheritance_per_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Parent directory specifies go=1.21 and fixture=1.0
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / ".eselect.conf").write_text('VM_GO="1.21"\nVM_FIXTURE=":1"\n')

    # Child directory specifies ONLY go=1.22 (fixture is unspecified)
    child_dir = parent_dir / "child"
    child_dir.mkdir()
    (child_dir / ".eselect.conf").write_text('VM_GO="1.22"\n')

    resolver = Resolver()

    # In child directory:
    # 1. 'go' resolves from child (.eselect.conf) -> 1.22.4
    res_go = resolver.resolve("go", current_dir=str(child_dir))
    assert res_go.selected_scope == Scope.PROJECT_FILE
    assert res_go.package.version == "1.22.4"

    # 2. 'fixture' is not specified in child, so it inherits from parent!
    res_fix = resolver.resolve("fixture", current_dir=str(child_dir))
    assert res_fix.selected_scope == Scope.PARENT_PROJECT
    assert res_fix.package.version == "1.0"


def test_user_default_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # User default conf
    user_conf = tmp_path / "config" / "eselect" / "version-manager.conf"
    user_conf.parent.mkdir(parents=True)
    user_conf.write_text('VM_GO="1.23"\n')

    resolver = Resolver()
    res = resolver.resolve("go", current_dir=str(empty_dir))

    assert res.selected_scope == Scope.USER_DEFAULT
    assert res.package.version == "1.23.1"


def test_system_default_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # System default conf in fake EROOT
    eroot = tmp_path / "eroot"
    sys_conf = eroot / "etc" / "eselect" / "version-manager.conf"
    sys_conf.parent.mkdir(parents=True)
    sys_conf.write_text('VM_GO="1.21"\n')

    resolver = Resolver(eroot=str(eroot))
    res = resolver.resolve("go", current_dir=str(empty_dir))

    assert res.selected_scope == Scope.SYSTEM_DEFAULT
    assert res.package.version == "1.21.5"


def test_invocation_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / ".eselect.conf").write_text('VM_GO="1.21"\n')

    resolver = Resolver()
    res = resolver.resolve("go", current_dir=str(proj_dir), overrides={"go": "1.23"})

    assert res.selected_scope == Scope.INVOCATION_OVERRIDE
    assert res.package.version == "1.23.1"


def test_unsatisfiable_selection_fails_strictly(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / ".eselect.conf").write_text('VM_GO=">=1.99"\n')

    resolver = Resolver()
    # Must FAIL, not fall back to system!
    with pytest.raises(NoMatchingVersionError) as exc_info:
        resolver.resolve("go", current_dir=str(proj_dir))
    assert "no installed version satisfies the requested constraint" in str(exc_info.value)


def test_recursion_detection(monkeypatch):
    monkeypatch.setenv("_ESELECT_VM_ACTIVE_TOOL", "go")
    resolver = Resolver()
    with pytest.raises(RecursionError):
        resolver.resolve("go")
