"""Deterministic project lookup, canonicalization, private project storage, and rebind."""

import hashlib
import os
from typing import Any, Dict, List, Optional, Tuple
from .config import (
    get_user_projects_dir,
    parse_declarative_config,
    update_config_file,
    tool_key,
    tool_from_key,
)
from .errors import StaleProjectRecordError, InvalidConfigError, VersionManagerError, ExitCode

PROJECT_ROOT_KEY = "PROJECT_ROOT"
PROJECT_CONFIG_FILENAME = ".eselect.conf"


def canonicalize_path(path: str) -> str:
    """Return the resolved absolute canonical filesystem path, eliminating symlinks."""
    return os.path.realpath(os.path.abspath(path))


def compute_project_id(canonical_path: str) -> str:
    """
    Compute stable SHA-256 digest of canonical absolute path.
    Used as filename <project-id>.conf in private user storage.
    """
    return hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()


def get_private_project_path_by_id(project_id: str) -> str:
    return os.path.join(get_user_projects_dir(), f"{project_id}.conf")


def get_private_project_config_path(canonical_path: str) -> str:
    return get_private_project_path_by_id(compute_project_id(canonical_path))


def get_project_file_path(project_root: str) -> str:
    return os.path.join(project_root, PROJECT_CONFIG_FILENAME)


def read_private_project_config(canonical_path: str) -> Optional[Dict[str, str]]:
    """
    Load private user-project configuration using O(1) path hash.
    Validates that recorded PROJECT_ROOT matches the queried path.
    """
    conf_path = get_private_project_config_path(canonical_path)
    if not os.path.exists(conf_path):
        return None

    project_id = compute_project_id(canonical_path)
    data = parse_declarative_config(conf_path)

    recorded_root = data.get(PROJECT_ROOT_KEY)
    if not recorded_root:
        raise StaleProjectRecordError(
            project_id=project_id,
            recorded_root="(none)",
            current_root=canonical_path,
            details={"file": conf_path, "reason": "missing PROJECT_ROOT in private project configuration"}
        )

    canonical_recorded = canonicalize_path(recorded_root)
    if canonical_recorded != canonical_path:
        raise StaleProjectRecordError(
            project_id=project_id,
            recorded_root=recorded_root,
            current_root=canonical_path,
            details={
                "file": conf_path,
                "reason": f"recorded PROJECT_ROOT '{recorded_root}' does not match '{canonical_path}'"
            }
        )

    return data


def save_private_project_config(canonical_path: str, updates: Dict[str, Optional[str]]) -> str:
    """Save or update private user-project configuration atomically."""
    conf_path = get_private_project_config_path(canonical_path)
    full_updates = dict(updates)
    full_updates[PROJECT_ROOT_KEY] = canonical_path
    update_config_file(
        conf_path,
        full_updates,
        header_comment=f"Private user project configuration for: {canonical_path}"
    )
    return conf_path


def delete_private_project_config(canonical_path: str) -> bool:
    """Delete private user-project configuration file if it exists."""
    conf_path = get_private_project_config_path(canonical_path)
    if os.path.exists(conf_path):
        try:
            os.remove(conf_path)
            return True
        except OSError as e:
            raise VersionManagerError(
                f"failed to delete private project configuration '{conf_path}': {e}",
                exit_code=ExitCode.GENERAL_ERROR,
                details={"file": conf_path, "error": str(e)}
            )
    return False


def rebind_project(old_path: str, new_path: str) -> Tuple[str, str]:
    """
    Explicitly rebind a moved project's private configuration from old_path to new_path.
    Returns (old_conf_path, new_conf_path).
    """
    old_canonical = canonicalize_path(old_path)
    new_canonical = canonicalize_path(new_path)

    old_conf = get_private_project_config_path(old_canonical)
    if not os.path.exists(old_conf):
        raise StaleProjectRecordError(
            project_id=compute_project_id(old_canonical),
            recorded_root=old_canonical,
            details={"reason": f"no private project configuration found for '{old_path}'"}
        )

    data = parse_declarative_config(old_conf)
    data[PROJECT_ROOT_KEY] = new_canonical

    new_conf = get_private_project_config_path(new_canonical)
    save_private_project_config(new_canonical, data)

    if old_conf != new_conf and os.path.exists(old_conf):
        try:
            os.remove(old_conf)
        except OSError:
            pass

    return old_conf, new_conf


def find_project_hierarchy(start_dir: str) -> List[Dict[str, Any]]:
    """
    Ascend from start_dir to filesystem root, identifying applicable project directories.
    Deterministic O(depth) lookup: checks for .eselect.conf and sha256 private config per ancestor.
    Returns list of project info dicts ordered from nearest (deepest) to root.
    """
    canonical_start = canonicalize_path(start_dir)
    current = canonical_start
    visited = set()
    hierarchy = []

    while current and current not in visited:
        visited.add(current)
        file_conf_path = get_project_file_path(current)
        has_file_conf = os.path.isfile(file_conf_path)

        private_conf_path = get_private_project_config_path(current)
        has_private_conf = os.path.isfile(private_conf_path)

        if has_file_conf or has_private_conf:
            hierarchy.append({
                "project_root": current,
                "has_file_conf": has_file_conf,
                "file_conf_path": file_conf_path if has_file_conf else None,
                "has_private_conf": has_private_conf,
                "private_conf_path": private_conf_path if has_private_conf else None,
            })

        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return hierarchy


def list_registered_private_projects() -> List[Dict[str, Any]]:
    """Enumerate all registered private projects in user storage for diagnostics and doctor."""
    projects_dir = get_user_projects_dir()
    if not os.path.isdir(projects_dir):
        return []

    results = []
    for entry in sorted(os.listdir(projects_dir)):
        if not entry.endswith(".conf"):
            continue
        full_path = os.path.join(projects_dir, entry)
        project_id = entry[:-5]
        try:
            cfg = parse_declarative_config(full_path)
            root = cfg.get(PROJECT_ROOT_KEY)
            is_valid = bool(root and os.path.isdir(root))
            is_stale = bool(root and not os.path.exists(root))
            results.append({
                "project_id": project_id,
                "config_file": full_path,
                "project_root": root,
                "is_valid": is_valid,
                "is_stale": is_stale,
                "config": cfg,
            })
        except Exception as e:
            results.append({
                "project_id": project_id,
                "config_file": full_path,
                "project_root": None,
                "is_valid": False,
                "is_stale": False,
                "error": str(e),
            })
    return results
