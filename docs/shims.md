# User-Local Shims and Execution

User-local shims are the primary dispatch mechanism for `eselect-version-manager`.

## Shim Location and Structure

Shims reside under:
`$HOME/.local/bin/eselect-version-manager/shims/`

Each shim is a thin, fast shell executable generated upon installation:

```bash
#!/usr/bin/env bash
# eselect-version-manager shim for go
set -e

DISPATCHER="${ESELECT_VM_DISPATCHER:-/usr/libexec/eselect-version-manager/dispatcher}"
exec "${DISPATCHER}" dispatch "go" "$@"
```

### PATH Activation

To activate shims in your interactive and non-interactive shell sessions, place the shims directory at the front of your `PATH`:

```bash
# Add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin/eselect-version-manager/shims:$PATH"
```

Or query the activation snippet dynamically:
```bash
eselect version-manager shims env
```

## Shim Management Lifecycle

### 1. Install
Creates executable shims for the requested tools (or all registered tools) and marks them enabled:
```bash
eselect version-manager shims install go
eselect version-manager shims install  # installs all available tools
```

### 2. Disable
Temporarily disables a shim without deleting the file or altering configured project/user selections:
```bash
eselect version-manager shims disable go
```
When a disabled shim is invoked, it bypasses `eselect-version-manager` resolution and delegates directly to the underlying system executable.

### 3. Enable
Re-enables a previously disabled shim:
```bash
eselect version-manager shims enable go
```

### 4. Uninstall
Removes the shim executable from `$HOME/.local/bin/eselect-version-manager/shims/`:
```bash
eselect version-manager shims uninstall go
```

### 5. List
Displays installed shims and their current status:
```bash
eselect version-manager shims list
```

Example output:
```text
Command          Tool         Status     Provider                         Path
--------------------------------------------------------------------------------
go               go           enabled    dev-lang/go                      /home/user/.local/bin/eselect-version-manager/shims/go
gofmt            go           enabled    dev-lang/go                      /home/user/.local/bin/eselect-version-manager/shims/gofmt
fixture-tool     fixture      disabled   app-misc/version-manager-fixture /home/user/.local/bin/eselect-version-manager/shims/fixture-tool
```

## Dispatch Overhead and Performance

The dispatcher is optimized for minimal startup overhead:
- **No shell evaluations** or arbitrary code sourcing.
- **Direct file checks** using path digests rather than directory listings.
- **Portage vartree caching** invalidated only when `/var/db/pkg` mtime changes.
- Typical dispatch resolution overhead is **under 5 milliseconds**, ensuring negligible impact on build tools and compiler invocations.
