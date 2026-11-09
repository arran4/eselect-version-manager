#!/usr/bin/env bash
# Real Gentoo end-to-end test execution inside Gentoo stage3 container.
# Strictly validates installation via emerge, module discovery, CLI, shims,
# non-root user execution, precedence, conversion, from-file, errors, and unmerge.
set -euo pipefail

echo "================================================================="
echo "=== Starting Gentoo End-to-End Test Suite in Portage Container ==="
echo "================================================================="

assert_contains() {
    local pattern="$1"
    local output="$2"
    if ! echo "${output}" | grep -F "${pattern}" >/dev/null; then
        echo "ASSERTION FAILED: '${pattern}' not found in output:" >&2
        echo "${output}" >&2
        return 1
    fi
}

# 1. Configure test overlay in Portage
echo "[Step 1] Setting up local Portage test overlay..."
mkdir -p /etc/portage/repos.conf
cat << 'EOF' > /etc/portage/repos.conf/test-overlay.conf
[test-overlay]
location = /workspace/packaging/test-overlay
priority = 100
auto-sync = false
EOF

mkdir -p /etc/portage/package.accept_keywords
cat << 'EOF' > /etc/portage/package.accept_keywords/version-manager
app-eselect/eselect-version-manager ~amd64
app-misc/version-manager-fixture ~amd64
app-misc/unslotted-fixture ~amd64
dev-lang/go ~amd64
EOF

# Ensure gentoo repo profile is linked
if [[ ! -e /etc/portage/make.profile ]]; then
    ln -s /var/db/repos/gentoo/profiles/default/linux/amd64/23.0 /etc/portage/make.profile
fi

# Disable sandbox features that require unshare privileges in docker
mkdir -p /etc/portage
echo 'FEATURES="-ipc-sandbox -network-sandbox -pid-sandbox"' >> /etc/portage/make.conf

# 2. Emerge packages from overlay
echo "[Step 2] Emerging eselect-version-manager and fixture packages..."
emerge --verbose --quiet-build=y \
    app-eselect/eselect-version-manager \
    app-misc/version-manager-fixture:1 \
    app-misc/version-manager-fixture:2 \
    app-misc/unslotted-fixture \
    dev-lang/go:1.22 \
    dev-lang/go:1.23

echo "Verifying packages in /var/db/pkg..."
test -d /var/db/pkg/app-eselect/eselect-version-manager-0.1.0
test -d /var/db/pkg/app-misc/version-manager-fixture-1.0
test -d /var/db/pkg/app-misc/version-manager-fixture-2.0
test -d /var/db/pkg/app-misc/unslotted-fixture-1.0
test -d /var/db/pkg/dev-lang/go-1.22.4
test -d /var/db/pkg/dev-lang/go-1.23.1
echo "✓ All packages successfully merged into Portage database!"

# 3. Verify eselect module discovery
echo "[Step 3] Verifying eselect module discovery..."
test -f /usr/share/eselect/modules/version-manager.eselect
MODULES_LIST=$(eselect modules list)
assert_contains "version-manager" "${MODULES_LIST}"
echo "✓ eselect discovers version-manager module!"

# 4. Verify system root CLI actions
echo "[Step 4] Testing root CLI actions..."
HELP_OUT=$(eselect version-manager help)
assert_contains "Manage per-project and user toolchain versions" "${HELP_OUT}"

LIST_OUT=$(eselect version-manager list)
assert_contains "app-misc/version-manager-fixture" "${LIST_OUT}"

LIST_FIX=$(eselect version-manager list fixture)
assert_contains "1.0 (slot 1)" "${LIST_FIX}"
assert_contains "2.0 (slot 2)" "${LIST_FIX}"
echo "✓ Root CLI commands functioning!"

# 5. Non-root user setup
echo "[Step 5] Setting up unprivileged testuser..."
id -u testuser >/dev/null 2>&1 || useradd -m -s /bin/bash testuser

cat << 'USER_TEST_SCRIPT_EOF' > /home/testuser/run_user_tests.sh
#!/usr/bin/env bash
set -euo pipefail

assert_contains() {
    local pattern="$1"
    local output="$2"
    if ! echo "${output}" | grep -F "${pattern}" >/dev/null; then
        echo "ASSERTION FAILED: '${pattern}' not found in output:" >&2
        echo "${output}" >&2
        return 1
    fi
}

export HOME="/home/testuser"
export XDG_CONFIG_HOME="${HOME}/.config"
export XDG_CACHE_HOME="${HOME}/.cache"
export XDG_STATE_HOME="${HOME}/.local/state"
export PATH="${HOME}/.local/bin/eselect-version-manager/shims:${PATH}"

echo "=== Running as non-root user $(whoami) ==="

# 6. Shim installation
echo "[Step 6] Installing user-local shims..."
eselect version-manager shims install
test -x "${HOME}/.local/bin/eselect-version-manager/shims/fixture-tool"
test -x "${HOME}/.local/bin/eselect-version-manager/shims/go"
test -x "${HOME}/.local/bin/eselect-version-manager/shims/unslotted-tool"
echo "✓ Shims installed and marked executable!"

# 7. Unslotted package execution through shim
echo "[Step 7] Testing unslotted fixture execution through shim..."
UNSLOTTED_OUT=$(unslotted-tool)
echo "  Output: ${UNSLOTTED_OUT}"
assert_contains "unslotted-tool version 1.0" "${UNSLOTTED_OUT}"
echo "✓ Unslotted toolchain dispatch verified!"

# 8. User default precedence
echo "[Step 8] Testing user-default precedence..."
eselect version-manager set --user fixture ":1"
OUT_SLOT1=$(fixture-tool)
echo "  User default slot 1 output: ${OUT_SLOT1}"
assert_contains "version 1.0 (slot 1)" "${OUT_SLOT1}"

eselect version-manager set --user fixture ":2"
OUT_SLOT2=$(fixture-tool)
echo "  User default slot 2 output: ${OUT_SLOT2}"
assert_contains "version 2.0 (slot 2)" "${OUT_SLOT2}"
echo "✓ User default switching verified!"

# 9. Private project selection & precedence
echo "[Step 9] Testing private project override..."
mkdir -p "${HOME}/projects/project_slot1"
cd "${HOME}/projects/project_slot1"
# In user defaults fixture is :2; set private project to :1
eselect version-manager set --project fixture ":1"
OUT_PROJ=$(fixture-tool)
echo "  Project override output: ${OUT_PROJ}"
assert_contains "version 1.0 (slot 1)" "${OUT_PROJ}"
# Outside project, must still be slot 2
cd "${HOME}"
OUT_OUTSIDE=$(fixture-tool)
assert_contains "version 2.0 (slot 2)" "${OUT_OUTSIDE}"
echo "✓ Private project isolation verified!"

# 10. Checked-in .eselect.conf reading
echo "[Step 10] Testing repository-local .eselect.conf..."
mkdir -p "${HOME}/projects/project_file"
cd "${HOME}/projects/project_file"
echo "VM_FIXTURE=\":1\"" > .eselect.conf
OUT_FILE=$(fixture-tool)
echo "  .eselect.conf output: ${OUT_FILE}"
assert_contains "version 1.0 (slot 1)" "${OUT_FILE}"
echo "✓ Checked-in .eselect.conf reading verified!"

# 11. Transactional conversion with --file
echo "[Step 11] Testing conversion between private user config and .eselect.conf..."
mkdir -p "${HOME}/projects/project_convert"
cd "${HOME}/projects/project_convert"
# First create private project selection
eselect version-manager set --project fixture ":1"
test ! -f .eselect.conf
# Convert with --file
eselect version-manager set --project --file fixture ":2"
test -f .eselect.conf
OUT_CONV=$(fixture-tool)
assert_contains "version 2.0 (slot 2)" "${OUT_CONV}"
# Convert back to user
eselect version-manager convert --to-user
test ! -f .eselect.conf
OUT_BACK=$(fixture-tool)
assert_contains "version 2.0 (slot 2)" "${OUT_BACK}"
echo "✓ Two-way conversion verified!"

# 12. Native from-file mode (Go adapter)
echo "[Step 12] Testing Go from-file adapter..."
mkdir -p "${HOME}/projects/go_project"
cd "${HOME}/projects/go_project"
cat << EOF > go.mod
module example.com/testmod

go 1.22
EOF
eselect version-manager set --project go from-file
GO_VER=$(go version)
echo "  Go 1.22 output: ${GO_VER}"
assert_contains "go1.22.4" "${GO_VER}"

# Update go.mod to toolchain 1.23.1
cat << EOF > go.mod
module example.com/testmod

go 1.22
toolchain go1.23.1
EOF
GO_VER2=$(go version)
echo "  Go 1.23 toolchain output: ${GO_VER2}"
assert_contains "go1.23.1" "${GO_VER2}"
echo "✓ Native from-file detection verified!"

# 13. Failure diagnostics on unsatisfiable constraint
echo "[Step 13] Testing failure diagnostics..."
mkdir -p "${HOME}/projects/fail_project"
cd "${HOME}/projects/fail_project"
echo "VM_GO=\">=1.99\"" > .eselect.conf
set +e
ERR_OUT=$(go 2>&1)
ERR_CODE=$?
set -e
echo "  Failing exit code: ${ERR_CODE}"
echo "  Diagnostics received:"
echo "${ERR_OUT}"
test "${ERR_CODE}" -eq 13
assert_contains "no installed version satisfies the requested constraint" "${ERR_OUT}"
assert_contains "emerge -pv" "${ERR_OUT}"
echo "✓ Diagnostic errors and stable exit codes verified!"

# 14. Shim lifecycle: disable, enable, uninstall
echo "[Step 14] Testing shim lifecycle..."
eselect version-manager shims disable fixture
SHIMS_DIS=$(eselect version-manager shims list)
assert_contains "disabled" "${SHIMS_DIS}"
eselect version-manager shims enable fixture
SHIMS_EN=$(eselect version-manager shims list)
assert_contains "enabled" "${SHIMS_EN}"
eselect version-manager shims uninstall fixture
test ! -f "${HOME}/.local/bin/eselect-version-manager/shims/fixture-tool"
echo "✓ Shim lifecycle verified!"

echo "[User Tests] All user tests completed successfully!"
USER_TEST_SCRIPT_EOF

chmod +x /home/testuser/run_user_tests.sh
chown testuser:testuser /home/testuser/run_user_tests.sh

su - testuser -c '/home/testuser/run_user_tests.sh'

# 15. Clean uninstallation of packages
echo "[Step 15] Testing clean package removal..."
emerge --unmerge --quiet \
    app-misc/version-manager-fixture \
    app-misc/unslotted-fixture \
    dev-lang/go \
    app-eselect/eselect-version-manager

test ! -f /usr/share/eselect/modules/version-manager.eselect
test ! -d /var/db/pkg/app-eselect/eselect-version-manager-0.1.0
echo "✓ Clean unmerge verified!"

echo "================================================================="
echo "=== ALL GENTOO END-TO-END INTEGRATION TESTS PASSED (15/15)    ==="
echo "================================================================="
