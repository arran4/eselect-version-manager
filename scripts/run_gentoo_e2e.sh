#!/usr/bin/env bash
# Runner for Gentoo stage3 container end-to-end test suite
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Pulling / preparing gentoo/portage container volume ==="
PORTAGE_DATA_CONTAINER=$(docker create gentoo/portage:latest)
trap 'docker rm -v "${PORTAGE_DATA_CONTAINER}" >/dev/null 2>&1 || true' EXIT

echo "=== Running Gentoo End-to-End Tests in Docker Container ==="
docker run --rm \
    --volumes-from "${PORTAGE_DATA_CONTAINER}" \
    -v "${WORKSPACE_ROOT}:/workspace" \
    gentoo/stage3:latest \
    /bin/bash /workspace/scripts/test_in_gentoo.sh
