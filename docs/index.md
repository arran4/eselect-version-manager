# eselect version-manager

Use different **Portage-installed** versions of development tools in different projects without changing the system's default selection.

The project provides an `eselect` module, a resolver and optional user-local executable shims. It does not download toolchains. See the [GitHub repository](https://github.com/arran4/eselect-version-manager) for its current development status.

## Start here

1. Install `app-eselect/eselect-version-manager` from the [companion Portage overlay](https://github.com/arran4/eselect-version-manager-overlay) when a release is available.
2. Enable only the shims you want: `eselect version-manager shims install go`.
3. Add `$HOME/.local/bin/eselect-version-manager/shims` before system tool directories in your `PATH`.
4. Inside a project, choose a version: `eselect version-manager set --project go 1.22`.
5. Check the decision: `eselect version-manager resolve go`.

## Select an installed version

```sh
eselect version-manager list go
eselect version-manager set --project go '>=1.22 <1.23'
eselect version-manager resolve go
go version
```

Use `--user` for a user-wide default, `--system` for an administrator default, and `--file` to write a shared `.eselect.conf`. A private project selection overrides a shared project file.

`latest` means the newest **installed** compatible package. `from-file` is opt-in; the Go provider reads `go.mod`/`go.work`.

## Technical reference

- [Scopes and precedence](precedence-and-scopes.md) — which selection takes effect.
- [Shims](shims.md) — install, disable and debug command dispatch.
- [Project files](conversion.md) — convert between private and checked-in settings.
- [Providers](providers.md) — how commands map to installed Gentoo packages.
- [Project lookup](project-lookup.md) — deterministic private project configuration.
- [Architecture](architecture.md) — components, package ownership and cache behaviour.

This website is **generated from the Markdown in `docs/`** by the GitHub Actions Pages workflow. It is not maintained separately.
