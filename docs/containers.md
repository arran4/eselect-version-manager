# Docker development, CI and demonstration images

One [multi-stage Dockerfile](https://github.com/arran4/eselect-version-manager/blob/main/Dockerfile) builds the installed tool, runs Gentoo end-to-end tests and creates a demonstration image.

| Target | Purpose |
| --- | --- |
| `installed` | Gentoo stage3 + Portage repository + real `app-eselect/eselect-version-manager` installed through `emerge` |
| `e2e` | Runs the full Gentoo test suite, including separate synthetic fixture packages; never published |
| `demo` | Non-root shell with active user-local shims and two explicitly synthetic slotted fixture tools |

The demo image provides a genuine Portage installation of the version manager. The `fixture-tool` executable is a demonstration fixture, **not** an actual Go, Python or Node.js replacement. It installs no mocked `dev-lang/go` packages.

## Run a published image

After the first GitHub release publishes the image to GHCR:

```sh
docker run --rm -it ghcr.io/arran4/eselect-version-manager:v0.1.0
```

Inside:

```sh
eselect version-manager list fixture
cd ~/projects/slot-1 && fixture-tool
cd ~/projects/slot-2 && fixture-tool
eselect version-manager resolve fixture
python3 --version
```

The two fixture projects use committed-style `.eselect.conf` files with `VM_FIXTURE=":1"` and `VM_FIXTURE=":2"`. This shows that project-aware selection works without changing a global `eselect` symlink.

The image runs as an unprivileged `demo` user. GitHub Packages visibility may need to be set to public before anonymous pulls work.

## Build locally from the current checkout

The [companion overlay](https://github.com/arran4/eselect-version-manager-overlay) must be checked out into `./overlay`:

```sh
git clone https://github.com/arran4/eselect-version-manager-overlay.git overlay
docker build --target demo --build-arg VM_SOURCE=checkout -t eselect-vm-demo .
docker run --rm -it eselect-vm-demo
```

Until the overlay migration PR merges, check out its `feat/seed-portage-overlay-and-fixtures` branch instead of the default branch.

To execute full Gentoo integration tests locally:

```sh
docker build --target e2e --build-arg VM_SOURCE=checkout --progress=plain .
```

This builds and installs the current source through the real Portage ebuild, then executes the end-to-end suite.

## CI and build cache

PR CI uses the `e2e` stage with Docker Buildx and the GitHub Actions cache (`type=gha`, `mode=max`). Cached immutable layers avoid re-copying the full Portage tree and reinstalling unchanged base dependencies on subsequent builds. When the application source changes, Portage package installation and E2E still run; no passing CI status is inferred from a different commit. Cache performance depends on available GitHub cache storage and source changes.

The Dockerfile pins the Gentoo stage3 and Portage image digests; update these deliberately.

## Release image

The [release-image workflow](https://github.com/arran4/eselect-version-manager/actions/workflows/release-image.yml) runs when a GitHub release is published with a version tag such as `v0.1.0`. It checks that the tag commit belongs to `main`, builds and tests the `e2e` target against the **tagged GitHub archive**, builds the `demo` target, smoke-tests it, then publishes `ghcr.io/arran4/eselect-version-manager:v0.1.0`.

The overlay must contain the matching versioned ebuild. The release Docker build generates a Manifest *inside the image* to validate the retrieved distfile. The companion overlay still needs its own **generated and committed release Manifest** before a normal user can `emerge` from it. Image publication must not be treated as evidence that this cross-repository packaging step is complete.

Do not push development or CI images to public release tags. Release images use a distinct verification path and `VM_SOURCE=release`, not an archive fabricated from the current checkout.
