# Configuration Conversion and the `--file` Option

`eselect-version-manager` distinguishes between private user-project configurations and repository-local `.eselect.conf` files, and provides transactional, two-way migration.

## Trust Boundaries

| Configuration Type | Location | Scope | Security Model |
| :--- | :--- | :--- | :--- |
| **Private User Project** | `~/.config/eselect/version-manager/projects/<sha256>.conf` | Local to user account | Trusted per-user settings |
| **Tracked Project File** | `<project-root>/.eselect.conf` | Committed to Git/VCS | Untrusted repository file (strictly declarative) |

## The `--file` Option

By default, setting a project toolchain version saves it as a private override:

```bash
eselect version-manager set --project go 1.26
```
This writes to `~/.config/eselect/version-manager/projects/<sha256>.conf`.

Passing `--file` directs the selection into the tracked `.eselect.conf`:

```bash
eselect version-manager set --project --file go 1.26
```

### Automatic Migration on `--file`
When `--file` is requested on a project that already has private user settings:
1. All existing private tool selections are read.
2. The new setting is merged with existing private settings.
3. The tracked `.eselect.conf` is written atomically.
4. Only after the file write succeeds are the migrated private selections cleaned up from user storage.

## Explicit Conversion Operations

### 1. Convert to File (`--to-file`)
Migrate all private user selections for a project into `.eselect.conf`:

```bash
eselect version-manager convert --to-file
```

- **Conflict Detection:** If `.eselect.conf` already exists and contains differing version constraints for the same tool, conversion aborts with exit code `18` (`CONVERSION_CONFLICT`).
- **Force Overwrite:**
  ```bash
  eselect version-manager convert --to-file --force
  ```

### 2. Convert to User (`--to-user`)
Migrate `.eselect.conf` selections into private user storage and remove the tracked file:

```bash
eselect version-manager convert --to-user
```

## Private Overrides for Team Projects

When a repository contains a checked-in `.eselect.conf`, individual developers can override settings locally without modifying git working trees:

```bash
eselect version-manager set --user-project go 1.27
```
This saves to private user storage and takes precedence over `.eselect.conf` in resolution.
