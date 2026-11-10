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

## Canonical release workflow

The [single CI/CD workflow](../.github/workflows/ci.yml) follows the repository-specific principles of the [canonical GitHub Actions reference](https://github.com/arran4/blog/blob/main/content/post/2026/043-canonical-github-actions-ci-cd-super-reference/index.md). The separate Pages workflow remains because Pages deployment has a different event and permission boundary.

From GitHub Actions → **CI** → Run workflow on `main`, choose `release-patch`, `release-minor` or `release-major`. For the **first** release, specify `release_version_override=0.1.0` explicitly; there is no previous tag from which to calculate a version. The workflow will:

1. Run Python validation and the real Gentoo container E2E against the selected commit.
2. Refuse to release if `main` advanced after testing, or the chosen tag already exists.
3. Push an immutable annotated `vX.Y.Z` tag.
4. In the **same workflow run**, check out that tag and fetch its real GitHub archive through Portage; run the tagged archive E2E and demo image smoke tests.
5. Push the verified `ghcr.io/arran4/eselect-version-manager:vX.Y.Z` image, then create the single GitHub Release.

External stable `vX.Y.Z` tag pushes use the same release gate. To retry a failed publication **without incrementing the version**, run the workflow with `publish-tag` and select that existing tag as the workflow ref. Do not move published tags. Pre-release SemVer suffixes are not supported yet because they need an explicit Portage PV translation.

The Docker build copies the reviewed `0.1.0` ebuild template to a temporary versioned ebuild *inside the build context* when required. This does not modify the companion overlay repository. Its independent release-update workflow detects published source releases and opens a separate, verified ebuild/Manifest PR.

No `9999` live ebuild is needed for this workflow: checkout builds already package the chosen source through the same ebuild, whereas release builds fetch the immutable tagged archive. Adding a live ebuild would be a separate opt-in capability, not a prerequisite.

The public image runs as an unprivileged `demo` user and contains **synthetic fixture commands**, not real slotted Go compilers. The GHCR package may need to be made public in package settings for anonymous pulls. **No first release exists until the workflow actually succeeds.**
