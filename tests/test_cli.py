"""Unit tests for command line dispatcher and actions."""

import os
from eselect_version_manager.cli import main
from eselect_version_manager.errors import ExitCode
from eselect_version_manager.project import (
    canonicalize_path,
    get_project_file_path,
    read_private_project_config,
)
from eselect_version_manager.config import get_user_config_path, parse_declarative_config


def test_cli_list(capsys=None):
    rc = main(["list"])
    assert rc == ExitCode.SUCCESS
    if capsys:
        captured = capsys.readouterr()
        assert "Available toolchains:" in captured.out
        assert "go" in captured.out
        assert "fixture" in captured.out


def test_cli_set_and_unset_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)

    canon_root = canonicalize_path(str(proj_dir))

    # 0. Rejection of invalid constraint before modifying any files
    rc_bad = main(["set", "go", ">>invalid"])
    assert rc_bad != ExitCode.SUCCESS
    assert not os.path.exists(get_project_file_path(canon_root))
    assert read_private_project_config(canon_root) is None

    # 1. Set private project selection (default for 'set')
    rc = main(["set", "go", "1.26"])
    assert rc == ExitCode.SUCCESS
    priv_data = read_private_project_config(canon_root)
    assert priv_data["VM_GO"] == "1.26"

    # 2. Set user default
    rc = main(["set", "--user", "go", "1.25"])
    assert rc == ExitCode.SUCCESS
    user_conf = get_user_config_path()
    assert parse_declarative_config(user_conf)["VM_GO"] == "1.25"

    # 3. Set with --file (converts private selections into .eselect.conf)
    rc = main(["set", "--file", "go", "1.24"])
    assert rc == ExitCode.SUCCESS
    file_path = get_project_file_path(canon_root)
    assert parse_declarative_config(file_path)["VM_GO"] == "1.24"
    # Private selection was cleaned up upon conversion
    assert read_private_project_config(canon_root) is None

    # 4. Unset in file
    rc = main(["unset", "--file", "go"])
    assert rc == ExitCode.SUCCESS
    assert "VM_GO" not in parse_declarative_config(file_path)


def test_cli_shims_workflow(tmp_path, monkeypatch, capsys=None):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    shims_dir = tmp_path / "shims"
    monkeypatch.setattr("eselect_version_manager.shims.get_shims_dir", lambda: str(shims_dir))

    # Install
    assert main(["shims", "install", "go"]) == ExitCode.SUCCESS
    assert (shims_dir / "go").is_file()

    # List
    assert main(["shims", "list"]) == ExitCode.SUCCESS
    if capsys:
        out = capsys.readouterr().out
        assert "go" in out
        assert "enabled" in out

    # Disable
    assert main(["shims", "disable", "go"]) == ExitCode.SUCCESS
    assert main(["shims", "list"]) == ExitCode.SUCCESS
    if capsys:
        out = capsys.readouterr().out
        assert "disabled" in out

    # Enable
    assert main(["shims", "enable", "go"]) == ExitCode.SUCCESS

    # Uninstall
    assert main(["shims", "uninstall", "go"]) == ExitCode.SUCCESS
    assert not (shims_dir / "go").exists()
