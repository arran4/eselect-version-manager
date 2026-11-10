# User-local shims

A shim is a small executable in `$HOME/.local/bin/eselect-version-manager/shims/`. Its filename matches the command, and it delegates to the installed dispatcher, which chooses a package-owned binary from Portage.

## Install and activate

```sh
eselect version-manager shims install go python maven
eselect version-manager shims list
```

Add this line to your interactive shell configuration:

```sh
export PATH="$HOME/.local/bin/eselect-version-manager/shims:$PATH"
```

Installing the ebuild does **not** automatically change your `PATH`. The shim directory must precede the system tool directories to intercept commands.

## Manage shims

```sh
eselect version-manager shims disable python
eselect version-manager shims enable python
eselect version-manager shims uninstall python
eselect version-manager doctor
```

Disabling keeps the configured version preferences and delegates to the existing system executable. Uninstalling removes user-local shim files, not Portage packages.

Use `ESELECT_VM_BYPASS=1 command` to bypass resolution for a single command. `eselect version-manager resolve <tool>` shows the winning configuration file, package and executable.

## Interpreter recursion

The dispatcher itself runs under Python. Therefore the **installed** dispatcher uses an absolute Python interpreter shebang (fixed by the ebuild) instead of `#!/usr/bin/env python3`. Otherwise a `python3` shim could invoke the dispatcher recursively.

The recursion guard also catches attempts to dispatch a command already active in the same process environment.

## Troubleshooting

- `command -v go` should point inside the user-local shim directory when enabled.
- `eselect version-manager shims list` shows installed shims and disabled entries.
- `eselect version-manager resolve go` explains an unsatisfied version, missing package-owned executable or malformed configuration.
- If no version is configured, the dispatcher delegates to the existing Gentoo/system executable. Explicitly requested but unavailable versions fail instead of falling back.
