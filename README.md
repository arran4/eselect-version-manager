# eselect-version-manager

Gentoo-native, project-aware toolchain version manager implemented as an `eselect` module.

`eselect-version-manager` bridges the gap between Gentoo's robust package management (Portage) and developer workflows requiring per-project toolchain versions (such as Go, Node, or Rust), without downloading unvetted third-party binaries, duplicating Portage functionality, or modifying system packages.

---

## Key Features

- **Gentoo Native:** Standard `app-admin/eselect` module (`version-manager.eselect`).
- **Portage Integrated:** Relies directly on Portage's installed package database (`/var/db/pkg`) and Gentoo version semantics (`vercmp`, revisions, slots).
- **User-Local Shims:** Unprivileged executable shims installed under `$HOME/.local/bin/eselect-version-manager/shims/`.
- **Deterministic O(depth) Project Lookup:** Uses SHA-256 canonical path hashing for sub-millisecond lookup, eliminating directory scanning on shim invocations.
- **Hierarchical Scopes & Precedence:** 6-tier precedence with per-tool inheritance in nested projects.
- **Transactional Conversion:** Seamlessly migrate between private user overrides and checked-in `.eselect.conf` files with `--file`, `--to-file`, and `--to-user`.
- **Declarative & Secure:** `.eselect.conf` is parsed strictly declaratively; arbitrary command substitution and shell execution are forbidden.
- **Native Version Detection:** Optional `from-file` mode reads `go.mod` and `go.work` toolchain directives while enforcing Portage management (`GOTOOLCHAIN=local`).

---

## Architecture Overview

```text
User Command ('go build', 'gofmt')
       ↓
User-Local PATH Shim ($HOME/.local/bin/eselect-version-manager/shims/<tool>)
       ↓
Shared Dispatcher / Resolver (/usr/libexec/eselect-version-manager/dispatcher)
       ↓
Resolve Version Constraint (Overrides -> Project -> User -> System)
       ↓
Inspect Portage Database (/var/db/pkg)
       ↓
Execute Installed Matching Binary (with Environment, e.g. GOROOT, GOTOOLCHAIN=local)
```

See [docs/architecture.md](docs/architecture.md) for full design details.

---

## Installation

### Local Overlay Installation

1. Add the repository or local ebuild to your Portage configuration:

```bash
mkdir -p /etc/portage/repos.conf
cat << 'EOF' > /etc/portage/repos.conf/eselect-version-manager.conf
[eselect-version-manager]
location = /var/db/repos/eselect-version-manager
priority = 100
auto-sync = false
EOF
```

2. Accept keywords:

```bash
echo "app-eselect/eselect-version-manager ~amd64" >> /etc/portage/package.accept_keywords/version-manager
```

3. Emerge the package:

```bash
emerge --verbose app-eselect/eselect-version-manager
```

4. Verify discovery:

```bash
eselect modules list | grep version-manager
eselect version-manager help
```

---

## User-Local Shim Setup

1. Install shims for your tools:

```bash
eselect version-manager shims install
```

2. Add the shims directory to your shell configuration (`~/.bashrc` or `~/.zshrc`):

```bash
export PATH="$HOME/.local/bin/eselect-version-manager/shims:$PATH"
```

3. Run the health check:

```bash
eselect version-manager doctor
```

---

## Precedence and Configuration Scopes

When a shim runs, tool versions resolve according to this strict hierarchy:

```text
Explicit Command Override (VM_OVERRIDE_<TOOL> or 'exec --tool')
        ↓
Nearest Project Selection (Private user-project overrides .eselect.conf)
        ↓
Parent Project Selection (for unspecified tools — per-tool inheritance)
        ↓
User-wide Default (~/.config/eselect/version-manager.conf)
        ↓
System-wide Default (/etc/eselect/version-manager.conf)
        ↓
Existing Gentoo-Selected / System Executable
```

See [docs/precedence-and-scopes.md](docs/precedence-and-scopes.md) for complete details.

---

## `.eselect.conf` Syntax and Examples

`.eselect.conf` files use familiar Gentoo-style variable assignments:

```bash
# Repository-local toolchain configuration
VM_GO=">=1.22 <1.23"
VM_NODE="22"
VM_PYTHON="system"
```

### Supported Version Constraints

| Selector | Meaning | Example |
| :--- | :--- | :--- |
| `1.22` | Series match (`=cat/pkg-1.22*`) | Matches 1.22.0, 1.22.4 |
| `1.22.4` | Exact version pin | Matches 1.22.4 only |
| `>=1.22 <1.23` | Bounded range | Matches any 1.22.x release |
| `latest` | Newest installed version | Newest compatible package in `/var/db/pkg` |
| `system` | Delegate to system default | Real binary outside shims |
| `:1.22` | Portage slot selector | Matches slot 1.22 |
| `from-file` | Native version detection | Reads `go.mod` / `go.work` |

---

## Private Overrides and `--file` Conversion

By default, selections are stored privately in user storage (`~/.config/eselect/version-manager/projects/<sha256>.conf`):

```bash
eselect version-manager set --project go 1.22
```

To create or convert to a tracked repository `.eselect.conf`:

```bash
# Converts private settings and writes .eselect.conf
eselect version-manager set --project --file go 1.22
```

### Conversion Commands

```bash
# Convert private user selections to .eselect.conf
eselect version-manager convert --to-file

# Force overwrite in case of conflicts
eselect version-manager convert --to-file --force

# Convert .eselect.conf back to private user storage
eselect version-manager convert --to-user
```

See [docs/conversion.md](docs/conversion.md) for conflict resolution and atomicity details.

---

## Native `from-file` Mode (Go)

`from-file` discovery is disabled by default and enabled explicitly per project:

```bash
eselect version-manager set --project go from-file
```

The Go adapter reads `go.work` (if present) or `go.mod`:
- `toolchain go1.22.4` directive specifies `>=1.22.4`.
- `go 1.22` directive specifies minimum version `>=1.22`.
- Sets `GOTOOLCHAIN=local` so Go never performs unapproved network toolchain downloads.

---

## Resolution Diagnostics and Error Handling

When resolution fails, `eselect-version-manager` prints a detailed diagnostic error to `stderr` with exit codes:

```text
eselect-version-manager: cannot resolve go: no installed version satisfies the requested constraint

Requested:   >=1.26 <1.27
Provider:    dev-lang/go
Installed:   1.22.4 (slot 1.22), 1.23.1 (slot 1.23)
Source:      .eselect.conf
Project:     /home/user/work/myproject
Suggestion:  emerge -pv 'dev-lang/go'
```

To view a detailed resolution explanation trace:

```bash
eselect version-manager resolve go
```

### Stable Exit Codes

- `0`: Success
- `2`: Invalid CLI invocation
- `10`: Unknown tool
- `11`: Invalid version constraint
- `12`: Invalid config syntax
- `13`: No matching installed version
- `14`: Missing executable in package
- `16`: Unsupported or missing native version file
- `17`: Stale or invalid private project record
- `18`: Conversion conflict
- `19`: Recursion detected

---

## Development and Testing

### Running Unit Tests

```bash
# Run standalone unit test runner (no dependencies required)
python3 tests/test_runner.py

# Or with pytest
python3 -m pytest tests/ -v
```

### Running Gentoo Container End-to-End Tests

```bash
./scripts/run_gentoo_e2e.sh
```

---

## Documentation Index

- [Architecture Overview](docs/architecture.md)
- [Precedence & Scopes](docs/precedence-and-scopes.md)
- [Project Lookup & Hashing](docs/project-lookup.md)
- [Configuration Conversion](docs/conversion.md)
- [User-Local Shims](docs/shims.md)
- [Generic Provider Architecture](docs/providers.md)
- [Upstream Adoption Guide](docs/upstream-adoption.md)

---

## License

Distributed under the terms of the GNU General Public License v2 or later (GPL-2+).
