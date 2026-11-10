"""Unit tests for Gentoo version comparison and constraint matching."""

try:
    import pytest
except ImportError:
    import tests.compat as pytest
import os
import shutil
import time
from eselect_version_manager.models import InstalledPackage
from eselect_version_manager.portage_backend import (
    vercmp,
    match_packages,
    get_installed_packages,
)
from eselect_version_manager.errors import InvalidVersionConstraintError


def test_vercmp_semantics():
    # Simple versions
    assert vercmp("1.21.5", "1.22.0") < 0
    assert vercmp("1.22.0", "1.21.5") > 0
    assert vercmp("1.22.4", "1.22.4") == 0

    # Revisions
    assert vercmp("1.22.4", "1.22.4-r1") < 0
    assert vercmp("1.22.4-r2", "1.22.4-r1") > 0

    # Suffixes
    assert vercmp("1.22_alpha1", "1.22_beta1") < 0
    assert vercmp("1.22_beta2", "1.22_rc1") < 0
    assert vercmp("1.22_rc1", "1.22") < 0
    assert vercmp("1.22", "1.22_p1") < 0


def create_pkg(cpv, slot="0"):
    cat, name_ver = cpv.split("/", 1)
    parts = name_ver.split("-")
    pkg_name = parts[0]
    ver_full = "-".join(parts[1:])
    if "-r" in ver_full:
        ver, rev = ver_full.split("-r")
        rev = f"r{rev}"
    else:
        ver, rev = ver_full, "r0"
    return InstalledPackage(
        cpv=cpv,
        category=cat,
        pkg_name=pkg_name,
        version=ver,
        revision=rev,
        slot=slot,
        subslot="",
        contents=[],
    )


def test_match_packages_latest():
    pkgs = [
        create_pkg("dev-lang/go-1.21.5", slot="1.21"),
        create_pkg("dev-lang/go-1.22.2", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
    ]
    matched = match_packages(pkgs, "dev-lang/go", "latest")
    assert len(matched) == 1
    assert matched[0].cpv == "dev-lang/go-1.22.4"


def test_match_packages_series():
    pkgs = [
        create_pkg("dev-lang/go-1.21.5", slot="1.21"),
        create_pkg("dev-lang/go-1.22.0", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
        create_pkg("dev-lang/go-1.220.1", slot="1.220"),
        create_pkg("dev-lang/go-1.23.0", slot="1.23"),
    ]
    # Series 1.22 should match 1.22.0 and 1.22.4, but NOT 1.220.1 or 1.23
    matched = match_packages(pkgs, "dev-lang/go", "1.22")
    cpvs = [p.cpv for p in matched]
    assert "dev-lang/go-1.22.0" in cpvs
    assert "dev-lang/go-1.22.4" in cpvs
    assert "dev-lang/go-1.220.1" not in cpvs
    assert "dev-lang/go-1.23.0" not in cpvs


def test_match_packages_exact_pin():
    pkgs = [
        create_pkg("dev-lang/go-1.22.2", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
    ]
    matched = match_packages(pkgs, "dev-lang/go", "1.22.4")
    assert len(matched) == 1
    assert matched[0].cpv == "dev-lang/go-1.22.4"


def test_match_packages_range():
    pkgs = [
        create_pkg("dev-lang/go-1.21.5", slot="1.21"),
        create_pkg("dev-lang/go-1.22.0", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
        create_pkg("dev-lang/go-1.23.1", slot="1.23"),
    ]
    matched = match_packages(pkgs, "dev-lang/go", ">=1.22 <1.23")
    cpvs = [p.cpv for p in matched]
    assert cpvs == ["dev-lang/go-1.22.0", "dev-lang/go-1.22.4"]


def test_match_packages_slot():
    pkgs = [
        create_pkg("app-misc/version-manager-fixture-1.0", slot="1"),
        create_pkg("app-misc/version-manager-fixture-2.0", slot="2"),
    ]
    matched_slot1 = match_packages(pkgs, "app-misc/version-manager-fixture", ":1")
    assert len(matched_slot1) == 1
    assert matched_slot1[0].slot == "1"

    matched_slot2 = match_packages(pkgs, "app-misc/version-manager-fixture", ":2")
    assert len(matched_slot2) == 1
    assert matched_slot2[0].slot == "2"


def test_match_packages_full_atom():
    pkgs = [
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
        create_pkg("dev-lang/go-1.23.0", slot="1.23"),
    ]
    matched = match_packages(pkgs, "dev-lang/go", "=dev-lang/go-1.22.4")
    assert len(matched) == 1
    assert matched[0].cpv == "dev-lang/go-1.22.4"


def test_slot_qualified_atom_matching():
    pkgs = [
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
        create_pkg("dev-lang/go-1.23.0", slot="1.23"),
    ]
    # Exact slot match
    matched = match_packages(pkgs, "dev-lang/go", "dev-lang/go:1.22")
    assert [p.cpv for p in matched] == ["dev-lang/go-1.22.4"]

    # Slot with operator
    matched_range = match_packages(pkgs, "dev-lang/go", ">=dev-lang/go-1.20:1.22")
    assert [p.cpv for p in matched_range] == ["dev-lang/go-1.22.4"]

    # Non-matching slot
    matched_empty = match_packages(pkgs, "dev-lang/go", "dev-lang/go:1.24")
    assert matched_empty == []


def test_revision_ordering_in_matching():
    pkgs = [
        create_pkg("dev-lang/go-1.22.4", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4-r1", slot="1.22"),
        create_pkg("dev-lang/go-1.22.4-r2", slot="1.22"),
    ]
    # Latest should select highest revision
    matched = match_packages(pkgs, "dev-lang/go", "latest")
    assert matched[0].cpv == "dev-lang/go-1.22.4-r2"

    # ~ match should include all revisions
    matched_tilde = match_packages(pkgs, "dev-lang/go", "~1.22.4")
    assert len(matched_tilde) == 3


def test_invalid_atom_raises_error():
    pkgs = [create_pkg("dev-lang/go-1.22.4", slot="1.22")]
    with pytest.raises(InvalidVersionConstraintError):
        match_packages(pkgs, "dev-lang/go", "invalid>>atom")


def test_cache_invalidation_on_package_add_and_revision(tmp_path, monkeypatch):
    """
    Test that cache invalidates immediately when packages/revisions are added or removed
    inside an existing category, without requiring /var/db/pkg directory mtime to change.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    eroot = tmp_path / "eroot"
    cat_dir = eroot / "var" / "db" / "pkg" / "dev-lang"
    cat_dir.mkdir(parents=True)

    # 1. Initially only go-1.22.4 is installed
    pkg1 = cat_dir / "go-1.22.4"
    pkg1.mkdir()
    (pkg1 / "SLOT").write_text("1.22\n")

    res1 = get_installed_packages("dev-lang/go", eroot=str(eroot))
    assert len(res1) == 1
    assert res1[0].version == "1.22.4"
    assert res1[0].revision == "r0"

    # Fix /var/db/pkg mtime in the past to ensure it does not change
    vartree = eroot / "var" / "db" / "pkg"
    os.utime(str(vartree), (1000000, 1000000))
    old_vartree_mtime = os.stat(str(vartree)).st_mtime_ns

    time.sleep(0.01)

    # 2. Add go-1.23.1 to existing category
    pkg2 = cat_dir / "go-1.23.1"
    pkg2.mkdir()
    (pkg2 / "SLOT").write_text("1.23\n")

    # Ensure /var/db/pkg mtime did not change
    assert os.stat(str(vartree)).st_mtime_ns == old_vartree_mtime

    res2 = get_installed_packages("dev-lang/go", eroot=str(eroot))
    assert len(res2) == 2
    assert [p.version for p in res2] == ["1.22.4", "1.23.1"]

    time.sleep(0.01)

    # 3. Add revision go-1.22.4-r1
    pkg1_r1 = cat_dir / "go-1.22.4-r1"
    pkg1_r1.mkdir()
    (pkg1_r1 / "SLOT").write_text("1.22\n")

    res3 = get_installed_packages("dev-lang/go", eroot=str(eroot))
    assert len(res3) == 3
    cpvs = [p.cpv for p in res3]
    assert "dev-lang/go-1.22.4-r1" in cpvs

    time.sleep(0.01)

    # 4. Unmerge go-1.22.4 (un-revised)
    shutil.rmtree(str(pkg1))

    res4 = get_installed_packages("dev-lang/go", eroot=str(eroot))
    assert len(res4) == 2
    cpvs_after = [p.cpv for p in res4]
    assert "dev-lang/go-1.22.4" not in cpvs_after
    assert "dev-lang/go-1.22.4-r1" in cpvs_after
