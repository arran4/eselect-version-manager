"""Unit tests for user-local shims management and lifecycle."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.shims import (
    ShimManager,
    is_shim_disabled,
    load_disabled_shims,
    save_disabled_shims,
)
from eselect_version_manager.errors import UnknownToolError, VersionManagerError


def test_shims_install_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"

    mgr = ShimManager(shims_dir=str(shims_dir))
    installed = mgr.install(["go"])

    assert "go" in installed
    assert "gofmt" in installed

    assert (shims_dir / "go").is_file()
    assert (shims_dir / "gofmt").is_file()
    assert os.access(str(shims_dir / "go"), os.X_OK)

    shim_list = mgr.list_shims()
    assert len(shim_list) == 2
    for s in shim_list:
        assert s["status"] == "enabled"


def test_shims_disable_and_enable(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"

    mgr = ShimManager(shims_dir=str(shims_dir))
    mgr.install(["go"])

    # Disable go
    mgr.disable(["go"])
    assert is_shim_disabled("go")
    assert is_shim_disabled("gofmt")

    shim_list = mgr.list_shims()
    for s in shim_list:
        assert s["status"] == "disabled"

    # Files must still exist on disk!
    assert (shims_dir / "go").is_file()

    # Re-enable
    mgr.enable(["go"])
    assert not is_shim_disabled("go")


def test_shims_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"

    mgr = ShimManager(shims_dir=str(shims_dir))
    mgr.install(["go"])

    mgr.uninstall(["go"])
    assert not (shims_dir / "go").exists()
    assert not (shims_dir / "gofmt").exists()
    assert len(mgr.list_shims()) == 0


def test_shims_install_rejects_unknown_tool(tmp_path, monkeypatch):
    """Attempting to install shims for an unsupported tool must fail explicitly."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"

    mgr = ShimManager(shims_dir=str(shims_dir))
    with pytest.raises(UnknownToolError) as exc_info:
        mgr.install(["unsupported-tool"])
    assert "unknown tool 'unsupported-tool'" in str(exc_info.value)
    assert not (shims_dir / "unsupported-tool").exists()


def test_shims_save_failure_raises_error(tmp_path, monkeypatch):
    """Writing disabled shims to an unwritable location must raise VersionManagerError."""
    # Point XDG_STATE_HOME to a file instead of dir to trigger OSError
    state_file = tmp_path / "state_blocked"
    state_file.write_text("blocked")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_file))

    with pytest.raises(VersionManagerError) as exc_info:
        save_disabled_shims({"go"})
    assert "failed to save shim state" in str(exc_info.value)


def test_shims_lifecycle_idempotency(tmp_path, monkeypatch):
    """Enabling, disabling, and installing shims must be completely idempotent."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"

    mgr = ShimManager(shims_dir=str(shims_dir))

    # Repeated install
    mgr.install(["go"])
    mgr.install(["go"])
    assert (shims_dir / "go").is_file()

    # Repeated disable
    mgr.disable(["go"])
    mgr.disable(["go"])
    assert is_shim_disabled("go")

    # Repeated enable
    mgr.enable(["go"])
    mgr.enable(["go"])
    assert not is_shim_disabled("go")
