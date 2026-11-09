# Architecture Overview

`eselect-version-manager` is a Gentoo-native, project-aware toolchain version manager implemented as an `eselect` module (`app-eselect/eselect-version-manager`).

## Core Philosophy

- **Portage owns package management:** Portage handles package dependencies, compilation, slotting, and installed package databases (`/var/db/pkg`). `eselect-version-manager` never downloads binaries, alters package files, or attempts to replace Portage.
- **`eselect-version-manager` owns selection and dispatch:** It identifies active toolchain versions across project, user, and system scopes and dispatches commands to the appropriate installed Portage binaries via user-local shims.
- **Zero maintainer overhead:** Standard Gentoo ebuild maintainers do not need to introduce special metadata files or registration manifests.

## High-Level Architecture Diagram

```
+-------------------------------------------------------------------+
|                        User Invocation                            |
|             (e.g., 'go build', 'gofmt', 'fixture-tool')           |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                 User-Local Shim ($HOME/.local/bin)                |
|           ~/.local/bin/eselect-version-manager/shims/<tool>       |
+-------------------------------------------------------------------+
                                  |
               executes with arguments, stdin/out/err
                                  |
                                  v
+-------------------------------------------------------------------+
|               Shared Dispatcher / Resolver Backend                |
|             /usr/libexec/eselect-version-manager/dispatcher       |
+-------------------------------------------------------------------+
         |                        |                       |
         v                        v                       v
+------------------+    +-------------------+   +--------------------+
|  Project Lookup  |    | Precedence Engine |   |  Portage Database  |
|  - .eselect.conf |    | - Invocation      |   |  - /var/db/pkg     |
|  - SHA-256 conf  |    | - Project scope   |   |  - Version match   |
|  - O(depth) hash |    | - User / System   |   |  - Slot & binaries |
+------------------+    +-------------------+   +--------------------+
                                  |
                     Resolves to target binary
                                  |
                                  v
+-------------------------------------------------------------------+
|           Installed Portage Binary (with Environment)             |
|       e.g., /usr/lib/go/1.22/bin/go [GOTOOLCHAIN=local, GOROOT]   |
+-------------------------------------------------------------------+
```

## Component Responsibilities

### 1. `modules/version-manager.eselect`
The thin Bash interface conforming strictly to Gentoo `eselect` standards:
- Clean modular structure with `describe_*` and `do_*` actions.
- Respects `ROOT`, `EROOT`, and `EPREFIX`.
- Contains no executable logic at global scope.
- Forwards subcommands to the backend dispatcher.

### 2. `eselect_version_manager/` (Python Package)
The shared resolution engine:
- **`config.py`**: Strictly declarative Gentoo-style assignment parser. Never invokes shell code or backticks. Provides atomic transactional file writing.
- **`project.py`**: Deterministic path canonicalization and O(depth) private project registration using SHA-256 digests.
- **`portage_backend.py`**: Native interface to Portage's vartree (`/var/db/pkg`), using Portage's `vercmp` and `match_from_list` algorithms with an mtime-invalidated cache.
- **`providers/`**: Generic provider abstraction mapping tool names to Portage package atoms, multi-command suites, environment variables, and native version file readers.
- **`resolver.py`**: Strict 6-tier precedence engine with detailed explanation capabilities.
- **`conversion.py`**: Predictable, transactional conversion between `.eselect.conf` and private project storage.
- **`shims.py`**: Management of executable shims in `$HOME/.local/bin/eselect-version-manager/shims/`.
- **`doctor.py`**: Diagnostic verification of PATH, permissions, and project health.

## Cache Invalidation Strategy

To minimize dispatcher latency on the hot execution path, package metadata can be cached in `${XDG_CACHE_HOME:-$HOME/.cache}/eselect/version-manager/portage_packages.json`.
- The cache stores the filesystem modification timestamp (`mtime`) of `/var/db/pkg`.
- Whenever Portage merges or unmerges any package, `/var/db/pkg`'s mtime changes automatically.
- If the mtime changes or the cache is missing or corrupted, the dispatcher performs a fast re-scan.
- A corrupted or missing cache never impacts user configuration.

## Recursion Safety and System Bypass

- **Recursion Guard:** When dispatching, `_ESELECT_VM_ACTIVE_TOOL=<command>` is exported into the environment. If a toolchain script or child process attempts to re-invoke the same shim recursively, the dispatcher aborts immediately with exit code `19` (`RECURSION_DETECTED`).
- **Bypass Mechanism:** If `VM_BYPASS=1` or `ESELECT_VM_BYPASS=1` is set in the environment, shims bypass resolution entirely and execute the underlying system binary from `PATH` directly.
