#!/usr/bin/env bash
# Calculate a stable Gentoo-compatible tag. Deliberately pure: no network,
# tag creation, checkout, or mutation. The CI job verifies the live git ref.
set -euo pipefail

mode="${1:-}"
override="${2:-}"
latest="${3:-}"

case "${mode}" in
    release-patch|release-minor|release-major) ;;
    *) printf 'Unsupported release mode: %s\n' "${mode}" >&2; exit 2 ;;
esac

if [[ -n "${override}" ]]; then
    tag="v${override#v}"
elif [[ -z "${latest}" ]]; then
    # First-release convention: the initial patch release is v0.1.0.
    # Initial major/minor releases are ambiguous without an explicit version.
    if [[ "${mode}" != "release-patch" ]]; then
        echo 'First release: use release-patch for v0.1.0 or supply release_version_override' >&2
        exit 2
    fi
    tag=v0.1.0
else
    if [[ ! "${latest}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        printf 'Invalid previous stable tag: %s\n' "${latest}" >&2
        exit 2
    fi
    IFS='.' read -r major minor patch <<< "${latest#v}"
    case "${mode}" in
        release-patch) patch=$((patch+1)) ;;
        release-minor) minor=$((minor+1)); patch=0 ;;
        release-major) major=$((major+1)); minor=0; patch=0 ;;
    esac
    tag="v${major}.${minor}.${patch}"
fi

if [[ ! "${tag}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    printf 'Invalid requested stable Gentoo version: %s\n' "${tag}" >&2
    exit 2
fi

printf '%s\n' "${tag}"
