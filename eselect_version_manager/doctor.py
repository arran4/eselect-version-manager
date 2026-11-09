"""Diagnostic health check tool (eselect version-manager doctor)."""

import os
import shutil
from typing import Dict, List, Tuple

from .config import (
    get_xdg_config_home,
    get_xdg_cache_home,
    get_xdg_state_home,
    get_shims_dir,
    get_system_config_path,
    get_user_config_path,
)
from .portage_backend import HAS_PORTAGE
from .project import list_registered_private_projects, canonicalize_path


def run_doctor(current_dir: str = None, eroot: str = None) -> Tuple[bool, List[str]]:
    """
    Perform comprehensive system health checks.
    Returns (all_passed, list_of_report_lines).
    """
    lines: List[str] = []
    lines.append("eselect-version-manager doctor health check:")
    lines.append("===========================================")

    all_passed = True

    # 1. PATH inspection
    shims_dir = os.path.realpath(get_shims_dir())
    path_dirs = [os.path.realpath(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]

    if shims_dir in path_dirs:
        shim_idx = path_dirs.index(shims_dir)
        lines.append(f"✓ PATH check: shims directory is present in PATH (priority #{shim_idx + 1})")
        lines.append(f"    Location: {shims_dir}")
    else:
        all_passed = False
        lines.append(f"✗ PATH check: shims directory is NOT in your PATH!")
        lines.append(f"    Suggested fix: add to your shell startup file (~/.bashrc or ~/.zshrc):")
        lines.append(f'      export PATH="{shims_dir}:$PATH"')

    # 2. Portage integration
    root = eroot or os.environ.get("EROOT") or "/"
    vartree = os.path.join(root, "var", "db", "pkg")
    if os.path.isdir(vartree):
        lines.append(f"✓ Portage vartree: {vartree} is accessible")
    else:
        lines.append(f"! Portage vartree: {vartree} not found (running outside Gentoo or minimal container)")

    if HAS_PORTAGE:
        lines.append("✓ Portage Python API: successfully imported official portage library")
    else:
        lines.append("! Portage Python API: not found (using portable standalone version engine)")

    # 3. Directory permissions
    for name, path in [
        ("Configuration", get_xdg_config_home()),
        ("Cache", get_xdg_cache_home()),
        ("State", get_xdg_state_home()),
        ("Shims", get_shims_dir()),
    ]:
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, ".test_write")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            lines.append(f"✓ {name} directory: {path} is writable")
        except OSError as e:
            all_passed = False
            lines.append(f"✗ {name} directory: {path} is NOT writable: {e}")

    # 4. Private project registrations
    registered = list_registered_private_projects()
    stale_count = sum(1 for p in registered if p.get("is_stale"))
    invalid_count = sum(1 for p in registered if not p.get("is_valid") and not p.get("is_stale"))

    if not registered:
        lines.append("✓ Registered private projects: 0 projects registered")
    else:
        lines.append(f"✓ Registered private projects: {len(registered)} total ({stale_count} stale, {invalid_count} corrupted)")
        for p in registered:
            if p.get("is_stale"):
                lines.append(f"    ! Stale project '{p['project_id']}': path '{p['project_root']}' no longer exists on disk")
                lines.append(f"        Suggestion: eselect version-manager rebind '{p['project_root']}' <new-path>")

    # 5. Current project check
    cwd = canonicalize_path(current_dir or os.getcwd())
    lines.append(f"✓ Current directory: {cwd}")

    lines.append("")
    if all_passed:
        lines.append("Doctor result: All critical checks passed.")
    else:
        lines.append("Doctor result: Some warnings or errors require attention.")

    return all_passed, lines
