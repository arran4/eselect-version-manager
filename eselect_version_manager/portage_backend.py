"""Gentoo Portage database inspection, version matching, and caching."""

import functools
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from .config import get_cache_dir, atomic_write_file
from .errors import InvalidVersionConstraintError
from .models import InstalledPackage

# Try importing official Portage modules
try:
    import portage
    import portage.dep as portage_dep
    import portage.versions as portage_versions
    HAS_PORTAGE = True
except ImportError:
    portage = None
    portage_dep = None
    portage_versions = None
    HAS_PORTAGE = False


# Pure Python fallback for version comparison when Portage is not installed (e.g. fast CI/unit tests)
GENTOO_VER_RE = re.compile(
    r'^(\d+(?:\.\d+)*[a-z]?)(?:_((?:alpha|beta|pre|rc|p)\d*))*(-r\d+)?$'
)
SUFFIX_PRIORITY = {
    "alpha": 1,
    "beta": 2,
    "pre": 3,
    "rc": 4,
    "p": 5,
}


def _split_gentoo_version(v: str) -> Tuple[List[int], str, List[Tuple[int, int]], int]:
    """Fallback parser for Gentoo package version strings."""
    m = GENTOO_VER_RE.match(v)
    if not m:
        # Simple numeric split fallback
        num_part = re.sub(r'[^0-9.]', '', v.split('-r')[0])
        nums = [int(x) for x in num_part.split('.') if x.isdigit()]
        r_part = int(v.split('-r')[1]) if '-r' in v else 0
        return (nums, "", [], r_part)

    base, suffixes, rev = m.groups()
    rev_num = int(rev[2:]) if rev else 0

    # Letter suffix
    letter = ""
    if base and base[-1].isalpha():
        letter = base[-1]
        base = base[:-1]

    nums = [int(x) for x in base.split(".") if x.isdigit()]

    # Suffixes (_alpha, _rc, etc.)
    parsed_sufs = []
    if suffixes:
        for s in re.finditer(r'_(alpha|beta|pre|rc|p)(\d*)', "_" + suffixes):
            kind, snum = s.group(1), s.group(2)
            parsed_sufs.append((SUFFIX_PRIORITY.get(kind, 0), int(snum) if snum else 0))

    return (nums, letter, parsed_sufs, rev_num)


def fallback_vercmp(v1: str, v2: str) -> int:
    """Fallback comparison of two Gentoo version strings when portage is absent."""
    if v1 == v2:
        return 0
    t1 = _split_gentoo_version(v1)
    t2 = _split_gentoo_version(v2)

    # Compare numeric components
    n1, n2 = t1[0], t2[0]
    max_len = max(len(n1), len(n2))
    p1 = n1 + [0] * (max_len - len(n1))
    p2 = n2 + [0] * (max_len - len(n2))
    if p1 != p2:
        return -1 if p1 < p2 else 1

    # Compare letter
    if t1[1] != t2[1]:
        return -1 if t1[1] < t2[1] else 1

    # Compare suffixes:
    # A release without suffix is newer than alpha/beta/pre/rc (priority 1..4),
    # but older than patchlevel _p (priority 5).
    s1, s2 = t1[2], t2[2]
    if s1 != s2:
        if not s1 and s2:
            # v1 has no suffix, v2 has suffix
            # if v2 is _p (priority 5), v2 > v1 -> return -1
            # else v2 is prerelease (priority < 5), v1 > v2 -> return 1
            return -1 if s2[0][0] >= 5 else 1
        elif s1 and not s2:
            # v1 has suffix, v2 has no suffix
            return 1 if s1[0][0] >= 5 else -1
        else:
            return -1 if s1 < s2 else 1

    # Compare revision
    if t1[3] != t2[3]:
        return -1 if t1[3] < t2[3] else 1

    return 0


def vercmp(v1: str, v2: str) -> int:
    """Compare two version strings using Portage's vercmp if available, else fallback."""
    if HAS_PORTAGE and portage_versions:
        return portage_versions.vercmp(v1, v2)
    return fallback_vercmp(v1, v2)


def get_installed_packages(provider_atom: str, eroot: Optional[str] = None) -> List[InstalledPackage]:
    """
    Query all installed packages matching provider_atom from Portage installed-package database.
    Checks and maintains an mtime-invalidated cache.
    """
    root = eroot or os.environ.get("EROOT") or "/"
    vartree_path = os.path.join(root, "var", "db", "pkg")

    # If vartree directory does not exist, return empty
    if not os.path.isdir(vartree_path):
        return []

    # Get vartree mtime for cache invalidation
    try:
        vartree_mtime = int(os.stat(vartree_path).st_mtime)
    except OSError:
        vartree_mtime = 0

    cache_file = os.path.join(get_cache_dir(), "portage_packages.json")
    cached = _read_cache(cache_file, vartree_mtime, provider_atom)
    if cached is not None:
        return cached

    # Inspect installed packages
    packages = _scan_installed_packages(root, provider_atom)

    # Write cache safely
    _write_cache(cache_file, vartree_mtime, provider_atom, packages)

    return packages


def _read_cache(cache_file: str, current_mtime: int, provider_atom: str) -> Optional[List[InstalledPackage]]:
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("vartree_mtime") != current_mtime:
            return None
        pkg_dicts = data.get("providers", {}).get(provider_atom)
        if pkg_dicts is None:
            return None
        return [InstalledPackage(**p) for p in pkg_dicts]
    except Exception:
        return None


def _write_cache(cache_file: str, current_mtime: int, provider_atom: str, packages: List[InstalledPackage]) -> None:
    try:
        existing_data = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                existing_data = {}

        if existing_data.get("vartree_mtime") != current_mtime:
            existing_data = {"vartree_mtime": current_mtime, "providers": {}}

        existing_data.setdefault("providers", {})[provider_atom] = [
            dataclasses_asdict(p) for p in packages
        ]
        atomic_write_file(cache_file, json.dumps(existing_data, indent=2))
    except Exception:
        # Cache failure must never prevent execution
        pass


def dataclasses_asdict(p: InstalledPackage) -> dict:
    return {
        "cpv": p.cpv,
        "category": p.category,
        "pkg_name": p.pkg_name,
        "version": p.version,
        "revision": p.revision,
        "slot": p.slot,
        "subslot": p.subslot,
        "contents": p.contents,
    }


def _scan_installed_packages(root: str, provider_atom: str) -> List[InstalledPackage]:
    """Scan /var/db/pkg using Portage API if available, or direct disk scan."""
    packages: List[InstalledPackage] = []

    # Clean provider atom category/name, e.g. "dev-lang/go"
    clean_cat_pkg = provider_atom.strip("=<>~:").split(":")[0]
    if "/" not in clean_cat_pkg:
        return []
    target_category, target_pkg = clean_cat_pkg.split("/", 1)

    vartree_path = os.path.join(root, "var", "db", "pkg", target_category)
    if not os.path.isdir(vartree_path):
        return []

    for entry in os.listdir(vartree_path):
        pkg_dir = os.path.join(vartree_path, entry)
        if not os.path.isdir(pkg_dir):
            continue

        # Check if package name matches (e.g. go-1.22.4 -> pkg name "go")
        if HAS_PORTAGE and portage_versions:
            split_res = portage_versions.pkgsplit(f"{target_category}/{entry}")
            if not split_res:
                continue
            cat_pkg, ver, rev = split_res
            entry_pkg_name = cat_pkg.split("/")[1]
        else:
            # Fallback split
            m = re.match(r'^(.+?)-(\d+(?:\.\d+)*[a-z]?(?:_(?:alpha|beta|pre|rc|p)\d*)*(?:-r\d+)?)$', entry)
            if not m:
                continue
            entry_pkg_name = m.group(1)
            full_ver = m.group(2)
            if "-r" in full_ver:
                ver, rev = full_ver.split("-r", 1)
                rev = f"r{rev}"
            else:
                ver, rev = full_ver, "r0"

        if entry_pkg_name != target_pkg:
            continue

        # Read package metadata (SLOT, CONTENTS)
        slot, subslot = "0", ""
        slot_file = os.path.join(pkg_dir, "SLOT")
        if os.path.isfile(slot_file):
            try:
                with open(slot_file, "r", encoding="utf-8") as f:
                    s_line = f.read().strip()
                    if "/" in s_line:
                        slot, subslot = s_line.split("/", 1)
                    else:
                        slot = s_line
            except OSError:
                pass

        contents = []
        contents_file = os.path.join(pkg_dir, "CONTENTS")
        if os.path.isfile(contents_file):
            try:
                with open(contents_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        # CONTENTS format: type path [hash mtime]
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] in ("obj", "sym"):
                            contents.append(parts[1])
            except OSError:
                pass

        packages.append(InstalledPackage(
            cpv=f"{target_category}/{entry}",
            category=target_category,
            pkg_name=target_pkg,
            version=ver,
            revision=rev,
            slot=slot,
            subslot=subslot,
            contents=contents,
        ))

    # Sort packages in ascending order
    def _pkg_sort_key(p: InstalledPackage):
        return functools.cmp_to_key(lambda a, b: vercmp(a.version, b.version))(p)

    packages.sort(key=lambda p: (functools.cmp_to_key(vercmp)(p.version), p.revision))
    return packages


def match_packages(
    packages: List[InstalledPackage],
    provider_atom: str,
    constraint: str
) -> List[InstalledPackage]:
    """
    Match installed packages against a constraint.
    Supports:
    - 'latest' -> returns highest version
    - Exact version: '1.26.3' -> =cat/pkg-1.26.3*
    - Series: '1.26' -> =cat/pkg-1.26*
    - Range: '>=1.26 <1.27'
    - Portage atoms: '=dev-lang/go-1.26.3', ':1.26' (slot)
    """
    if not packages:
        return []

    c = constraint.strip()
    if c == "latest":
        return [packages[-1]] if packages else []

    clean_provider = provider_atom.strip("=<>~:").split(":")[0]

    # Handle slot selector, e.g. ':1.26'
    if c.startswith(":"):
        target_slot = c[1:]
        return [p for p in packages if p.slot == target_slot]

    # Handle multiple spaced expressions (e.g. '>=1.26 <1.27')
    terms = c.split()
    matched = list(packages)

    for term in terms:
        atom = _normalize_term_to_atom(clean_provider, term)
        matched = _filter_by_atom(matched, atom)
        if not matched:
            break

    return matched


def _normalize_term_to_atom(clean_provider: str, term: str) -> str:
    """Convert user version term into full Gentoo atom."""
    # If already a full package atom with category, return as is
    if "/" in term:
        return term

    # If starts with operator
    for op in (">=", "<=", ">", "<", "=", "~"):
        if term.startswith(op):
            val = term[len(op):]
            return f"{op}{clean_provider}-{val}"

    # If it is a series like '1.26' (only 2 numeric components, e.g. major.minor)
    # Series match in Gentoo is '=cat/pkg-1.26*'
    parts = term.split(".")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return f"={clean_provider}-{term}*"

    # Default to exact match
    return f"={clean_provider}-{term}"


def _filter_by_atom(packages: List[InstalledPackage], atom: str) -> List[InstalledPackage]:
    """Filter list of installed packages by a single Portage atom."""
    cpv_list = [p.cpv for p in packages]
    matched_cpvs = set()

    if HAS_PORTAGE and portage_dep:
        try:
            matched_cpvs = set(portage_dep.match_from_list(atom, cpv_list))
        except Exception:
            matched_cpvs = set()

    if not matched_cpvs:
        # Fallback filtering logic
        matched_cpvs = _fallback_match_atom(packages, atom)

    return [p for p in packages if p.cpv in matched_cpvs]


def _fallback_match_atom(packages: List[InstalledPackage], atom: str) -> set:
    """Fallback atom matching when portage is not present."""
    matched = set()
    # Match operator
    op_m = re.match(r'^(>=|<=|>|<|=|~)?([^=<>~]+)$', atom)
    if not op_m:
        return matched
    op = op_m.group(1) or "="
    target = op_m.group(2)

    is_wildcard = target.endswith("*")
    if is_wildcard:
        target = target[:-1]

    # Extract version from target
    m = re.search(r'-(\d+(?:\.\d+)*[a-z]?(?:_(?:alpha|beta|pre|rc|p)\d*)*(?:-r\d+)?)$', target)
    if not m:
        return matched
    target_ver = m.group(1)

    for p in packages:
        cmp_res = vercmp(p.version, target_ver)
        if op == "=":
            if is_wildcard:
                if p.version == target_ver or (
                    p.version.startswith(target_ver)
                    and len(p.version) > len(target_ver)
                    and not p.version[len(target_ver)].isdigit()
                ):
                    matched.add(p.cpv)
            else:
                if cmp_res == 0:
                    matched.add(p.cpv)
        elif op == ">=":
            if cmp_res >= 0:
                matched.add(p.cpv)
        elif op == "<=":
            if cmp_res <= 0:
                matched.add(p.cpv)
        elif op == ">":
            if cmp_res > 0:
                matched.add(p.cpv)
        elif op == "<":
            if cmp_res < 0:
                matched.add(p.cpv)
        elif op == "~":
            if p.version.split("-")[0] == target_ver.split("-")[0]:
                matched.add(p.cpv)

    return matched
