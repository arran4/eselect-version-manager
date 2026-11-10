# Architecture

The `eselect` module is a command-line interface. A Python dispatcher performs project lookup, queries Portage's installed package database and executes the selected binary. It does not install packages or change system-wide `eselect` symlinks.

```text
PATH shim (go, python3, mvn, ...)
    → dispatcher
    → project/private/user/system preference lookup
    → Portage VDB package matching (version, SLOT, CONTENTS)
    → package-owned executable + provider environment
```

## Components

| Path | Responsibility |
| --- | --- |
| `modules/version-manager.eselect` | Standard `eselect` actions |
| `eselect_version_manager/cli.py` | Command parsing and messages |
| `project.py`, `config.py` | Canonical project roots and declarative configuration |
| `resolver.py` | Scope precedence, errors and execution target |
| `portage_backend.py` | Installed packages, version constraints and cache |
| `providers/` | Package-to-command mappings; Go, Python and Maven support |
| `shims.py` | User-local shim lifecycle |
| `conversion.py` | Copy selections between private storage and `.eselect.conf` |

The dispatcher trusts a candidate binary only when it is executable and appears in the selected package's installed `CONTENTS` metadata. This prevents selecting a package by version and executing a different package's `/usr/bin` wrapper.

## Package inventory and caching

Portage's installed package database under `/var/db/pkg` is authoritative. Cache entries live under `$XDG_CACHE_HOME/eselect/version-manager/`. Invalidation inspects the relevant category, installed package entries and Portage's update counter; it does not rely solely on the top-level VDB directory timestamp.

A cache miss or corrupt cache triggers a fresh scan. Package installation, upgrade and removal are tested in the Gentoo container suite.

## Recursion and bypass

The dispatcher sets `_ESELECT_VM_ACTIVE_TOOL` for an active command, failing when a shim calls itself again. `ESELECT_VM_BYPASS=1` (also `VM_BYPASS=1`) delegates to the existing system command.

The installed Python dispatcher must use an absolute interpreter shebang fixed by the Gentoo ebuild. Using `/usr/bin/env python3` would re-enter a `python3` shim if the shim directory precedes `/usr/bin`.

## Gentoo boundaries

Portage installs toolchains and defines which versions may coexist. Existing `eselect` modules continue to manage system defaults. Project selections alter only the command process and descendants.

The separate [companion overlay](https://github.com/arran4/eselect-version-manager-overlay) contains the ebuild. Its synthetic CI packages are isolated under `tests/portage-overlay`, not installed on normal machines.
