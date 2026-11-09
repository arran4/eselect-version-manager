"""Configuration file paths, declarative parser, and atomic writer."""

import os
import re
import shlex
import tempfile
from typing import Dict, List, Optional, Tuple
from .errors import InvalidConfigError


def get_xdg_config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def get_xdg_cache_home() -> str:
    return os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")


def get_xdg_state_home() -> str:
    return os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")


def get_system_config_dir(eroot: Optional[str] = None) -> str:
    root = eroot or os.environ.get("EROOT") or "/"
    return os.path.normpath(os.path.join(root, "etc/eselect"))


def get_system_config_path(eroot: Optional[str] = None) -> str:
    return os.path.join(get_system_config_dir(eroot), "version-manager.conf")


def get_user_config_dir() -> str:
    return os.path.join(get_xdg_config_home(), "eselect")


def get_user_config_path() -> str:
    return os.path.join(get_user_config_dir(), "version-manager.conf")


def get_user_projects_dir() -> str:
    return os.path.join(get_user_config_dir(), "version-manager", "projects")


def get_cache_dir() -> str:
    return os.path.join(get_xdg_cache_home(), "eselect", "version-manager")


def get_state_dir() -> str:
    return os.path.join(get_xdg_state_home(), "eselect", "version-manager")


def get_shims_dir() -> str:
    # Per specification: $HOME/.local/bin/eselect-version-manager/shims/
    home = os.path.expanduser("~")
    return os.path.join(home, ".local", "bin", "eselect-version-manager", "shims")


# Regex for strictly declarative Gentoo-style variable assignment:
# Matches KEY=VALUE where KEY is [A-Za-z_][A-Za-z0-9_]*
ASSIGNMENT_RE = re.compile(r'^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)$')


def parse_declarative_config(path: str) -> Dict[str, str]:
    """
    Parse a Gentoo-style configuration file strictly declaratively.
    Never evaluates shell code, commands or backticks.
    Preserves comments and validates syntax.
    """
    if not os.path.exists(path):
        return {}

    values: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise InvalidConfigError(path, f"failed to read file: {e}")

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        m = ASSIGNMENT_RE.match(line)
        if not m:
            raise InvalidConfigError(
                path,
                f"syntax error on line {lineno}: expected KEY=\"value\", got: {stripped}",
                details={"line_number": lineno, "content": stripped}
            )

        key, raw_val = m.group(1), m.group(2).strip()

        # Check for dangerous backticks or $() command substitutions
        if "`" in raw_val or "$(" in raw_val:
            raise InvalidConfigError(
                path,
                f"security violation on line {lineno}: command substitution is forbidden",
                details={"line_number": lineno, "content": stripped}
            )

        # Parse quoted string or bare value
        val = _extract_value(raw_val, path, lineno)
        values[key] = val

    return values


def _extract_value(raw_val: str, path: str, lineno: int) -> str:
    """Extract unquoted value from raw assignment rhs, stripping trailing comments if unquoted."""
    if not raw_val:
        return ""

    first_char = raw_val[0]
    if first_char in ('"', "'"):
        quote_char = first_char
        end_idx = -1
        escaped = False
        for i in range(1, len(raw_val)):
            if raw_val[i] == "\\" and quote_char == '"':
                escaped = not escaped
                continue
            if raw_val[i] == quote_char and not escaped:
                end_idx = i
                break
            escaped = False

        if end_idx == -1:
            raise InvalidConfigError(path, f"unclosed quote on line {lineno}", details={"line_number": lineno})

        content = raw_val[1:end_idx]
        remainder = raw_val[end_idx + 1:].strip()
        if remainder and not remainder.startswith("#"):
            raise InvalidConfigError(path, f"trailing characters after closing quote on line {lineno}", details={"line_number": lineno})

        # Process simple escape sequences if double-quoted
        if quote_char == '"':
            content = content.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\t', '\t')
        return content

    # Unquoted value: take until whitespace or comment
    parts = raw_val.split(None, 1)
    val = parts[0]
    if "#" in val:
        val = val.split("#", 1)[0]
    return val


def atomic_write_file(path: str, content: str, mode: int = 0o644) -> None:
    """
    Atomically write content to path using a temporary file in the same directory.
    Ensures safe permissions and transactional updates.
    """
    dirname = os.path.dirname(os.path.abspath(path))
    os.makedirs(dirname, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(prefix=".tmp_eselect_", dir=dirname, text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def update_config_file(path: str, updates: Dict[str, Optional[str]], header_comment: str = "") -> None:
    """
    Update or unset keys in a Gentoo-style configuration file.
    Preserves existing unrelated entries, order, and comments.
    If value is None, the key is unset (removed).
    If file doesn't exist, it is created.
    """
    existing_lines: List[str] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()
        except OSError as e:
            raise InvalidConfigError(path, f"failed to read file: {e}")

    remaining_keys = set(updates.keys())
    new_lines: List[str] = []

    for line in existing_lines:
        m = ASSIGNMENT_RE.match(line)
        if m:
            key = m.group(1)
            if key in updates:
                new_val = updates[key]
                remaining_keys.discard(key)
                if new_val is not None:
                    new_lines.append(f'{key}="{new_val}"\n')
                # If new_val is None, key is removed (omitted)
                continue
        new_lines.append(line)

    # Append any remaining new keys
    if remaining_keys:
        # If adding to an empty or comment-only file, add header if provided
        if not existing_lines and header_comment:
            new_lines.append(f"# {header_comment}\n")
        elif new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        for key in sorted(remaining_keys):
            val = updates[key]
            if val is not None:
                new_lines.append(f'{key}="{val}"\n')

    atomic_write_file(path, "".join(new_lines))


def tool_key(tool: str) -> str:
    """Format tool name as config variable name, e.g. 'go' -> 'VM_GO'."""
    clean = re.sub(r'[^A-Za-z0-9_]', '_', tool).upper()
    return f"VM_{clean}"


def tool_from_key(key: str) -> Optional[str]:
    """Extract tool name from config key if it starts with VM_."""
    if key.startswith("VM_"):
        return key[3:].lower()
    return None
