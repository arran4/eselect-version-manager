# eselect-version-manager

Per-project versions of **Portage-installed** tools, managed through an `eselect` module and user-local PATH shims. The project does not install or download toolchains.

**Status:** [initial implementation PR #1](https://github.com/arran4/eselect-version-manager/pull/1) is under review. The package is not released.

**Technical documentation:** [arran4.github.io/eselect-version-manager](https://arran4.github.io/eselect-version-manager/) (site available after GitHub Pages is enabled and the documentation workflow is deployed). The site is **generated** from the Markdown in [`docs/`](docs/) by GitHub Actions; edit the source Markdown rather than generated HTML.

## Quick start

The [companion overlay](https://github.com/arran4/eselect-version-manager-overlay) contains the proposed `app-eselect/eselect-version-manager` ebuild. The current version requires a source archive built from this draft branch; do not expect a published distfile until the first release.

After installing the module on Gentoo:

```sh
eselect version-manager help
eselect version-manager shims install go
# Add once to your shell startup file:
export PATH="$HOME/.local/bin/eselect-version-manager/shims:$PATH"
```

Set a private project selection:

```sh
cd ~/work/example
eselect version-manager set --project go '>=1.22 <1.23'
eselect version-manager resolve go
go version
```

Or write a project file to share with colleagues:

```sh
eselect version-manager set --project --file go 1.22
# writes .eselect.conf; commit it if appropriate
```

Private project settings override matching values in `.eselect.conf`. Unspecified tools inherit from parent projects, user defaults and system defaults. An explicit unsatisfied version fails rather than running an unrelated version.

`from-file` is opt-in: `eselect version-manager set --project go from-file` reads the applicable `go.mod`/`go.work`.

## Docker demo

The source [Dockerfile](Dockerfile) has `e2e` and `demo` stages. [Docker guide](docs/containers.md) documents local builds and the versioned GHCR demo image built after a release. The demo uses clearly labelled slotted fixture tools; it does not include mock Go compilers.

## Documentation and development

The [technical documentation](docs/index.md) covers [selection scopes](docs/precedence-and-scopes.md), [shims](docs/shims.md), [configuration migration](docs/conversion.md), [provider support](docs/providers.md), [project lookup](docs/project-lookup.md) and [architecture](docs/architecture.md).

```sh
python3 tests/test_runner.py
# With the companion overlay checked out at ./overlay:
./scripts/run_gentoo_e2e.sh
# Build the generated Pages documentation locally:
python3 -m pip install -r docs/requirements.txt
mkdocs build --strict
```

The Gentoo end-to-end test uses disposable Portage fixtures supplied by the companion overlay. The fixture `dev-lang/go` packages are mocks, **not real Go backports**.

Licence: GPL-2+.
