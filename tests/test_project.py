"""Unit tests for project canonicalization, private storage, and hierarchy."""

import os
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.project import (
    canonicalize_path,
    compute_project_id,
    read_private_project_config,
    save_private_project_config,
    delete_private_project_config,
    rebind_project,
    find_project_hierarchy,
    list_registered_private_projects,
    get_project_file_path,
    PROJECT_ROOT_KEY,
)
from eselect_version_manager.errors import StaleProjectRecordError


def test_canonicalize_and_project_id(tmp_path):
    real_dir = tmp_path / "actual"
    real_dir.mkdir()
    sym_dir = tmp_path / "symlink"
    sym_dir.symlink_to(real_dir)

    canon_real = canonicalize_path(str(real_dir))
    canon_sym = canonicalize_path(str(sym_dir))

    assert canon_real == canon_sym
    id1 = compute_project_id(canon_real)
    id2 = compute_project_id(canon_sym)
    assert id1 == id2
    assert len(id1) == 64  # SHA-256 hex length


def test_private_project_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    canon_proj = canonicalize_path(str(proj_dir))

    # Initially empty
    assert read_private_project_config(canon_proj) is None

    # Save
    conf_path = save_private_project_config(canon_proj, {"VM_GO": "1.26"})
    assert os.path.isfile(conf_path)

    # Read
    data = read_private_project_config(canon_proj)
    assert data is not None
    assert data[PROJECT_ROOT_KEY] == canon_proj
    assert data["VM_GO"] == "1.26"

    # Delete
    assert delete_private_project_config(canon_proj) is True
    assert read_private_project_config(canon_proj) is None


def test_stale_project_record_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    proj_dir = tmp_path / "project_a"
    proj_dir.mkdir()
    canon_a = canonicalize_path(str(proj_dir))

    # Save for project A
    save_private_project_config(canon_a, {"VM_GO": "1.26"})

    # Corrupt configuration to point to another directory
    conf_path = (tmp_path / "config" / "eselect" / "version-manager" / "projects" / f"{compute_project_id(canon_a)}.conf")
    conf_path.write_text('PROJECT_ROOT="/nonexistent/path"\nVM_GO="1.26"\n')

    with pytest.raises(StaleProjectRecordError) as exc_info:
        read_private_project_config(canon_a)
    assert "stale or invalid private project record" in str(exc_info.value)


def test_rebind_project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    old_dir = tmp_path / "old_proj"
    new_dir = tmp_path / "new_proj"
    old_dir.mkdir()
    new_dir.mkdir()

    old_canon = canonicalize_path(str(old_dir))
    new_canon = canonicalize_path(str(new_dir))

    save_private_project_config(old_canon, {"VM_GO": "1.26"})
    old_conf, new_conf = rebind_project(old_canon, new_canon)

    assert not os.path.exists(old_conf)
    assert os.path.exists(new_conf)

    new_data = read_private_project_config(new_canon)
    assert new_data[PROJECT_ROOT_KEY] == new_canon
    assert new_data["VM_GO"] == "1.26"


def test_project_hierarchy_nearest_and_nested(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Create root / parent / child
    parent_dir = tmp_path / "parent"
    child_dir = parent_dir / "child"
    sub_dir = child_dir / "deep" / "nested"
    sub_dir.mkdir(parents=True)

    # Parent has .eselect.conf
    (parent_dir / ".eselect.conf").write_text('VM_GO="1.22"\nVM_NODE="20"\n')

    # Child has private config
    child_canon = canonicalize_path(str(child_dir))
    save_private_project_config(child_canon, {"VM_GO": "1.26"})

    hierarchy = find_project_hierarchy(str(sub_dir))
    assert len(hierarchy) == 2

    # Nearest is child
    assert hierarchy[0]["project_root"] == child_canon
    assert hierarchy[0]["has_private_conf"] is True
    assert hierarchy[0]["has_file_conf"] is False

    # Parent is second
    parent_canon = canonicalize_path(str(parent_dir))
    assert hierarchy[1]["project_root"] == parent_canon
    assert hierarchy[1]["has_file_conf"] is True
