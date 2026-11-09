# Selection Scopes and Precedence

`eselect-version-manager` enforces a deterministic 6-tier precedence hierarchy for every managed toolchain.

## Precedence Hierarchy

```text
1. Explicit Command / Invocation Override
      ↓
2. Nearest Project Selection (Private User-Project overrides .eselect.conf)
      ↓
3. Parent Project Selection (per-tool inheritance in nested projects)
      ↓
4. User-wide Default (~/.config/eselect/version-manager.conf)
      ↓
5. System-wide Default (/etc/eselect/version-manager.conf)
      ↓
6. Existing Gentoo-Selected / System Executable
```

## Detailed Scope Definitions

### 1. Command Invocation Override
- **Sources:**
  - Environment variable: `VM_OVERRIDE_<TOOL>` (e.g., `VM_OVERRIDE_GO="1.23"`)
  - CLI execution override: `eselect version-manager exec --tool go=1.23 -- go build`
- **Behavior:** Takes unconditional precedence over all filesystem configuration.

### 2. Nearest Project Selection
- Checked in the canonical directory containing the executed command or its nearest ancestor project.
- **Within the same project root:**
  - Private user-project selection (`~/.config/eselect/version-manager/projects/<sha256>.conf`) overrides `.eselect.conf`.
  - Enables developers to override team configurations locally without modifying tracked git files.

### 3. Parent Project Selection (Nested Projects & Inheritance)
- When projects are nested (e.g., a monorepo or submodule), the nearest project configuration takes precedence.
- **Inheritance is strictly per tool:**
  - If a child project defines `VM_GO="1.26"`, it overrides the parent's Go setting.
  - If the child project does *not* specify `VM_NODE`, it inherits `VM_NODE` from the parent project.

### 4. User-wide Default
- **Location:** `${XDG_CONFIG_HOME:-$HOME/.config}/eselect/version-manager.conf`
- Applies to all projects where the specific tool is not defined at the project level.
- Managed via:
  ```bash
  eselect version-manager set --user go 1.26
  eselect version-manager unset --user go
  ```

### 5. System-wide Default
- **Location:** `/etc/eselect/version-manager.conf` (respects Gentoo `EROOT`)
- Machine-wide fallback defaults managed by system administrators:
  ```bash
  eselect version-manager set --system go system
  ```

### 6. System Executable Fallback
- If a tool is explicitly set to `system` or remains unspecified across all configuration layers, the dispatcher delegates to the system-installed executable in `PATH` (excluding the user-local shims directory).

## Strict Failure Policy

An explicit version constraint that cannot be satisfied by an installed Portage package **must fail immediately**.
- `eselect-version-manager` **never silently falls back** to another version or to the system default when an explicit constraint is present.
- A failing resolution terminates with exit code `13` (`NO_MATCHING_VERSION`) and prints diagnostic troubleshooting suggestions.
