"""Transactional conversion between private user-project configuration and .eselect.conf."""

import os
from typing import Any, Dict, Optional, Tuple

from .config import (
    parse_declarative_config,
    update_config_file,
    tool_key,
    tool_from_key,
)
from .errors import ConversionConflictError
from .project import (
    canonicalize_path,
    get_project_file_path,
    get_private_project_config_path,
    read_private_project_config,
    save_private_project_config,
    delete_private_project_config,
    PROJECT_ROOT_KEY,
)


def convert_to_file(
    project_root: str,
    force: bool = False,
    additional_updates: Optional[Dict[str, Optional[str]]] = None
) -> Dict[str, Any]:
    """
    Convert private user-project selections into checked-in .eselect.conf.
    Preserves existing unrelated .eselect.conf entries.
    Detects conflicts and requires force=True to overwrite divergent file settings.
    Atomically writes .eselect.conf BEFORE removing migrated private settings.
    Idempotent on repeated calls.
    """
    canonical_root = canonicalize_path(project_root)
    file_path = get_project_file_path(canonical_root)

    # 1. Read private config
    priv_conf = read_private_project_config(canonical_root) or {}
    priv_tools = {k: v for k, v in priv_conf.items() if k.startswith("VM_")}

    # 2. Read existing file config
    existing_file_conf = {}
    if os.path.isfile(file_path):
        existing_file_conf = parse_declarative_config(file_path)

    # Apply any additional updates (e.g. from 'set --project --file')
    merged_updates = dict(priv_tools)
    if additional_updates:
        merged_updates.update(additional_updates)

    if not merged_updates and not os.path.isfile(file_path):
        return {
            "converted": {},
            "conflicts": {},
            "file_path": file_path,
            "private_removed": False,
        }

    # 3. Detect conflicts between existing .eselect.conf and migrating selections
    conflicts = {}
    for key, new_val in merged_updates.items():
        if key in existing_file_conf and existing_file_conf[key] != new_val:
            # If not explicitly updated in this transaction, it is a conflict
            if not additional_updates or key not in additional_updates:
                conflicts[key] = {
                    "file_value": existing_file_conf[key],
                    "private_value": new_val,
                }

    if conflicts and not force:
        conflict_desc = "\n".join(
            f"  {k}: .eselect.conf has '{v['file_value']}', private config has '{v['private_value']}'"
            for k, v in conflicts.items()
        )
        raise ConversionConflictError(
            f"conversion conflict in '{canonical_root}':\n{conflict_desc}",
            details={"conflicts": str(conflicts)}
        )

    # 4. Transactional write to .eselect.conf
    update_config_file(
        file_path,
        merged_updates,
        header_comment=f"eselect-version-manager project configuration"
    )

    # 5. After successful file write, clean up migrated private configuration
    private_removed = False
    if priv_tools:
        # Remove migrated keys from private config
        remaining_priv = {k: v for k, v in priv_conf.items() if not k.startswith("VM_")}
        if len(remaining_priv) <= 1 and PROJECT_ROOT_KEY in remaining_priv:
            # Only PROJECT_ROOT was left; delete entire private file
            delete_private_project_config(canonical_root)
            private_removed = True
        else:
            # Unset migrated keys
            unsets = {k: None for k in priv_tools.keys()}
            save_private_project_config(canonical_root, unsets)

    return {
        "converted": {k: v for k, v in merged_updates.items() if v is not None},
        "conflicts": conflicts,
        "file_path": file_path,
        "private_removed": private_removed,
    }


def convert_to_user(project_root: str, force: bool = False) -> Dict[str, Any]:
    """
    Convert checked-in .eselect.conf selections into private user-project configuration.
    Preserves existing unrelated entries.
    Detects conflicts and requires force=True to overwrite divergent user settings.
    Atomically writes private config BEFORE removing migrated file settings.
    Idempotent on repeated calls.
    """
    canonical_root = canonicalize_path(project_root)
    file_path = get_project_file_path(canonical_root)

    if not os.path.isfile(file_path):
        return {
            "converted": {},
            "conflicts": {},
            "file_path": file_path,
            "file_removed": False,
        }

    file_conf = parse_declarative_config(file_path)
    file_tools = {k: v for k, v in file_conf.items() if k.startswith("VM_")}

    # Read existing private config
    priv_conf = read_private_project_config(canonical_root) or {}

    # Detect conflicts
    conflicts = {}
    for key, val in file_tools.items():
        if key in priv_conf and priv_conf[key] != val:
            conflicts[key] = {
                "private_value": priv_conf[key],
                "file_value": val,
            }

    if conflicts and not force:
        conflict_desc = "\n".join(
            f"  {k}: private config has '{v['private_value']}', .eselect.conf has '{v['file_value']}'"
            for k, v in conflicts.items()
        )
        raise ConversionConflictError(
            f"conversion conflict in '{canonical_root}':\n{conflict_desc}",
            details={"conflicts": str(conflicts)}
        )

    # 1. Transactional write to private configuration
    save_private_project_config(canonical_root, file_tools)

    # 2. After private write succeeds, remove migrated keys from .eselect.conf
    remaining_file_keys = [k for k in file_conf.keys() if not k.startswith("VM_")]
    file_removed = False
    if not remaining_file_keys:
        try:
            os.remove(file_path)
            file_removed = True
        except OSError:
            pass
    else:
        unsets = {k: None for k in file_tools.keys()}
        update_config_file(file_path, unsets)

    return {
        "converted": file_tools,
        "conflicts": conflicts,
        "file_path": file_path,
        "file_removed": file_removed,
    }
