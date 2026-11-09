"""Unit tests for Gentoo version comparison and constraint matching."""

try:
    import pytest
except ImportError:
    import tests.compat as pytest
from eselect_version_manager.models import InstalledPackage
from eselect_version_manager.portage_backend import vercmp, match_packages


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
