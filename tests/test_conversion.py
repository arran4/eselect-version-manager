"""Unit tests for transactional configuration conversion (--to-file and --to-user)."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.conversion import convert_to_file, convert_to_user
from eselect_version_manager.project import (
    canonicalize_path,
    save_private_project_config,
    read_private_project_config,
    get_project_file_path,
)
from eselect_version_manager.config import parse_declarative_config
from eselect_version_manager.errors import ConversionConflictError


def test_convert_to_file_success(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    canon_root = canonicalize_path(str(proj_dir))
    file_path = get_project_file_path(canon_root)

    # 1. Existing .eselect.conf has VM_NODE="20"
    (proj_dir / ".eselect.conf").write_text('VM_NODE="20"\n')

    # 2. Private config has VM_GO="1.26"
    save_private_project_config(canon_root, {"VM_GO": "1.26"})

    # 3. Convert to file
    res = convert_to_file(canon_root)
    assert res["converted"]["VM_GO"] == "1.26"

    # Verify .eselect.conf now has both VM_NODE and VM_GO
    file_data = parse_declarative_config(file_path)
    assert file_data["VM_NODE"] == "20"
    assert file_data["VM_GO"] == "1.26"

    # Verify private config was cleaned up
    assert read_private_project_config(canon_root) is None

    # Idempotent repeated run
    res_repeat = convert_to_file(canon_root)
    assert res_repeat["converted"] == {}


def test_convert_to_file_conflict_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    canon_root = canonicalize_path(str(proj_dir))

    # Existing file has VM_GO="1.22"
    (proj_dir / ".eselect.conf").write_text('VM_GO="1.22"\n')

    # Private config has divergent VM_GO="1.26"
    save_private_project_config(canon_root, {"VM_GO": "1.26"})

    # Without force, must raise ConversionConflictError
    with pytest.raises(ConversionConflictError) as exc_info:
        convert_to_file(canon_root, force=False)
    assert "conversion conflict" in str(exc_info.value)

    # With force=True, overwrites
    res = convert_to_file(canon_root, force=True)
    assert res["converted"]["VM_GO"] == "1.26"
    file_data = parse_declarative_config(get_project_file_path(canon_root))
    assert file_data["VM_GO"] == "1.26"


def test_convert_to_user_success(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    canon_root = canonicalize_path(str(proj_dir))

    # .eselect.conf has VM_GO="1.26"
    (proj_dir / ".eselect.conf").write_text('VM_GO="1.26"\n')

    # Convert to user
    res = convert_to_user(canon_root)
    assert res["converted"]["VM_GO"] == "1.26"

    # Private config now has VM_GO
    priv_data = read_private_project_config(canon_root)
    assert priv_data["VM_GO"] == "1.26"

    # .eselect.conf was removed (as all keys were migrated)
    assert not os.path.exists(get_project_file_path(canon_root))
