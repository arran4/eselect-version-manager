#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
script=scripts/calculate_release_tag.sh

expect_tag() {
    local want="$1"
    shift
    local got
    got="$(bash "$script" "$@")"
    if [[ "$got" != "$want" ]]; then
        printf 'Expected %s, got %s for [%s]\n' "$want" "$got" "$*" >&2
        exit 1
    fi
}

expect_failure() {
    if bash "$script" "$@" >/dev/null 2>&1; then
        printf 'Expected invalid request to fail: [%s]\n' "$*" >&2
        exit 1
    fi
}

# No stable tags: the initial patch workflow must Just Work.
expect_tag v0.1.0 release-patch "" ""
expect_tag v0.1.0 release-patch
expect_failure release-minor "" ""
expect_failure release-major "" ""

# Explicit bootstrap and recovery overrides (also allow the leading v).
expect_tag v0.1.0 release-patch 0.1.0 ""
expect_tag v0.2.0 release-minor v0.2.0 ""
expect_tag v1.0.0 release-major 1.0.0 ""

# Once released, all three bump types use the latest stable tag.
expect_tag v0.1.1 release-patch "" v0.1.0
expect_tag v0.2.0 release-minor "" v0.1.0
expect_tag v1.0.0 release-major "" v0.1.0
expect_tag v2.0.0 release-major "" v1.8.11

# Explicit overrides are authoritative but always validated.
expect_tag v0.1.9 release-patch v0.1.9 v0.1.0
expect_failure release-patch 0.1.0-rc1 ""
expect_failure release-patch 01.2.3 ""
expect_failure release-patch "" v0.1.0-rc1
expect_failure release-patch "" v0.1
expect_failure release-hotfix "" v0.1.0

echo "Release tag calculation tests passed"
