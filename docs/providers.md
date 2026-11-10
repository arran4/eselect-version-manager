# Toolchain providers

A provider maps a tool name to one Portage package and the executable names the user can shim. It selects only **installed** package versions. For example, `go 1.26` is shorthand for a version-series constraint on `dev-lang/go`, not a toolchain download.

## Included providers

| Tool | Gentoo package | Shim commands | Notes |
| --- | --- | --- | --- |
| Go | `dev-lang/go` | `go`, `gofmt` | `from-file` reads `go.mod`/`go.work`; sets `GOTOOLCHAIN=local` |
| Python | `dev-lang/python` | `python`, `python3` | Uses package-owned `python3.13`, `python3.14`, etc.; leaves `python-exec` system defaults unchanged |
| Maven | `dev-java/maven-bin` | `mvn` | Selects the existing `mvn-${SLOT}` script; Java runtime selection stays with Gentoo's Java tools |

Go versions can only run side by side if the installed ebuilds genuinely permit it. Gentoo already provides separately slotted Python interpreters and Maven versions; **no copied Python/Maven ebuilds are required**.

```sh
eselect version-manager shims install python maven
eselect version-manager list python
eselect version-manager list maven
eselect version-manager set --project python ':3.14'
eselect version-manager set --project maven ':3.10'
python3 --version
mvn --version
```

An unsatisfied selection fails. `system` delegates to existing system selectors. Neither Python nor Maven currently implements `from-file`; it remains an explicit opt-in for Go.

## Define a generic provider

Create `~/.config/eselect/version-manager/providers.d/example.conf`:

```sh
PACKAGE_ATOM="dev-util/example"
COMMANDS="example example-helper"
```

Then install the shim and select an installed package version:

```sh
eselect version-manager shims install example
eselect version-manager set --project example latest
```

Provider configuration is declarative. Commands must be owned by the selected installed package; a provider cannot invent a binary path or download software.

Providers with the same name follow user-over-system precedence. To replace a built-in provider, set `OVERRIDE_BUILTIN="true"` explicitly. A command may have only one provider owner; use a provider-name override rather than defining another provider that silently steals a command.

## Environment and native requirements

The Go provider sets `GOROOT` when appropriate and `GOTOOLCHAIN=local` to avoid implicit downloads. Python relies on a package-owned versioned interpreter; Maven uses its Gentoo-provided versioned script and the existing Java runtime selection.

Custom environment synthesis requires a programmatic provider adapter rather than executable shell code in `.eselect.conf`. This is a version selector, not an environment-script runner.

The synthetic test providers live in the [separate CI fixture overlay](https://github.com/arran4/eselect-version-manager-overlay/tree/feat/seed-portage-overlay-and-fixtures/tests/portage-overlay). Their fake Go ebuilds are not real toolchain backports.
