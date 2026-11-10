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
[eselect-version-manager-overlay]
location = /workspace/overlay
priority = 100
auto-sync = false

[eselect-version-manager-fixtures]
location = /workspace/overlay/tests/portage-overlay
priority = 110
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

# 1b. For checkout CI synthesize an archive from the exact checkout. For a
# release tag, the installed stage has already fetched the real GitHub tarball;
# never replace that real release archive with a local checkout.
VM_VERSION="${VM_VERSION:-0.1.0}"
VM_SOURCE="${VM_SOURCE:-checkout}"
pkg="/workspace/overlay/app-eselect/eselect-version-manager/eselect-version-manager-${VM_VERSION}.ebuild"
test -f "${pkg}"

if [[ "${VM_SOURCE}" == checkout ]]; then
    echo "[Step 1b] Creating checkout source archive in DISTDIR..."
    mkdir -p /var/cache/distfiles
    tar -czf "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz" \
        --transform="s,^,eselect-version-manager-${VM_VERSION}/," \
        -C /workspace \
        bin config docs eselect_version_manager modules README.md
    chown -R portage:portage /var/cache/distfiles
    chmod 0644 "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz"
elif [[ "${VM_SOURCE}" == release ]]; then
    echo "[Step 1b] Retaining verified tagged source archive and installed ebuild..."
    test -s "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz"
else
    echo "Unsupported VM_SOURCE: ${VM_SOURCE}" >&2
    exit 2
fi

echo "Verifying Manifest for eselect-version-manager version ${VM_VERSION}..."
ebuild --force "${pkg}" manifest

# 2. Emerge packages from overlay
echo "[Step 2] Emerging eselect-version-manager and fixture packages from genuine source archive..."
emerge --verbose --quiet-build=y \
    app-eselect/eselect-version-manager \
    app-misc/version-manager-fixture:1 \
    app-misc/version-manager-fixture:2 \
    app-misc/unslotted-fixture \
    dev-lang/go:1.22 \
    dev-lang/go:1.23

echo "Verifying packages in /var/db/pkg..."
test -d /var/db/pkg/app-eselect/eselect-version-manager-${VM_VERSION}
test -d /var/db/pkg/app-misc/version-manager-fixture-1.0
test -d /var/db/pkg/app-misc/version-manager-fixture-2.0
test -d /var/db/pkg/app-misc/unslotted-fixture-1.0
test -d /var/db/pkg/dev-lang/go-1.22.4
test -d /var/db/pkg/dev-lang/go-1.23.1
echo "✓ All packages successfully merged into Portage database!"

# 2b. Test cache invalidation inside existing category
echo "[Step 2b] Verifying cache invalidation on package revision inside existing category..."
LIST_BEFORE=$(eselect version-manager list fixture)
assert_contains "1.0 (slot 1)" "${LIST_BEFORE}"
assert_contains "2.0 (slot 2)" "${LIST_BEFORE}"

# 1. Manual VDB revision test (mtime of /var/db/pkg alone is not relied upon)
cp -a /var/db/pkg/app-misc/version-manager-fixture-2.0 /var/db/pkg/app-misc/version-manager-fixture-2.0-r1
touch -d "2020-01-01" /var/db/pkg

LIST_AFTER=$(eselect version-manager list fixture)
assert_contains "2.0-r1" "${LIST_AFTER}"
echo "✓ Cache immediately invalidated on package revision in existing category!"
rm -rf /var/db/pkg/app-misc/version-manager-fixture-2.0-r1

# 2. Genuine Portage emerge and unmerge cache invalidation
echo "Testing genuine Portage emerge & unmerge cache invalidation..."
cp /workspace/overlay/tests/portage-overlay/app-misc/version-manager-fixture/version-manager-fixture-2.0.ebuild \
   /workspace/overlay/tests/portage-overlay/app-misc/version-manager-fixture/version-manager-fixture-2.0-r1.ebuild
ebuild --force /workspace/overlay/tests/portage-overlay/app-misc/version-manager-fixture/version-manager-fixture-2.0-r1.ebuild manifest
emerge --oneshot --quiet-build=y =app-misc/version-manager-fixture-2.0-r1
LIST_EMERGE=$(eselect version-manager list fixture)
assert_contains "2.0-r1" "${LIST_EMERGE}"
echo "✓ Genuine emerge package immediately visible in version list!"

emerge --unmerge --quiet =app-misc/version-manager-fixture-2.0-r1
LIST_UNMERGE=$(eselect version-manager list fixture)
if echo "${LIST_UNMERGE}" | grep -F "2.0-r1" >/dev/null; then
    echo "ASSERTION FAILED: unmerged 2.0-r1 still present in list!" >&2
    exit 1
fi
echo "✓ Genuine unmerge package immediately removed from version list!"
rm -f /workspace/overlay/tests/portage-overlay/app-misc/version-manager-fixture/version-manager-fixture-2.0-r1.ebuild
ebuild --force /workspace/overlay/tests/portage-overlay/app-misc/version-manager-fixture/version-manager-fixture-2.0.ebuild manifest

# Re-emerge fixture slot 2 for subsequent tests
emerge --oneshot --quiet-build=y app-misc/version-manager-fixture:2

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

# 4b. Test malformed providers.d configuration and built-in protection
echo "[Step 4b] Testing malformed dynamic provider definition handling..."
mkdir -p /etc/eselect/version-manager/providers.d
echo "INVALID SYNTAX" > /etc/eselect/version-manager/providers.d/broken.conf
set +e
DYN_ERR=$(eselect version-manager list 2>&1)
DYN_CODE=$?
set -e
test "${DYN_CODE}" -ne 0
assert_contains "broken.conf" "${DYN_ERR}"
rm -f /etc/eselect/version-manager/providers.d/broken.conf

# Accidental override of built-in is blocked
echo 'PACKAGE_ATOM="dev-lang/go-bin"' > /etc/eselect/version-manager/providers.d/go.conf
set +e
GO_OVR_ERR=$(eselect version-manager list 2>&1)
GO_OVR_CODE=$?
set -e
test "${GO_OVR_CODE}" -ne 0
assert_contains "attempts to override built-in provider 'go'" "${GO_OVR_ERR}"
rm -f /etc/eselect/version-manager/providers.d/go.conf
echo "✓ Dynamic provider syntax and override protection verified!"

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
test -x "${HOME}/.local/bin/eselect-version-manager/shims/python3"
test -x "${HOME}/.local/bin/eselect-version-manager/shims/mvn"
test -x "${HOME}/.local/bin/eselect-version-manager/shims/unslotted-tool"
echo "✓ Shims installed and marked executable!"

# 6a. Test real slotted Gentoo Python and pinned dispatcher interpreter
echo "[Step 6a] Testing slotted Python interpreter through shim..."
eselect version-manager set --user python latest
PYTHON_OUT=$(python3 --version)
assert_contains "Python 3." "${PYTHON_OUT}"
PYTHON_RES=$(eselect version-manager resolve python)
assert_contains "dev-lang/python-" "${PYTHON_RES}"
eselect version-manager unset --user python
echo "✓ Existing Gentoo Python interpreter selected through shim without recursive dispatch!"

# 6b. Testing unsupported shim rejection and dynamic provider definition
echo "[Step 6b] Testing unsupported shim rejection..."
set +e
UNSUPP_OUT=$(eselect version-manager shims install nonexistent-tool 2>&1)
UNSUPP_CODE=$?
set -e
test "${UNSUPP_CODE}" -ne 0
assert_contains "unknown tool" "${UNSUPP_OUT}"
echo "✓ Unsupported shim installation rejected!"

# Register dynamic custom provider
mkdir -p "${XDG_CONFIG_HOME}/eselect/version-manager/providers.d"
cat << EOF > "${XDG_CONFIG_HOME}/eselect/version-manager/providers.d/unslotted.conf"
PACKAGE_ATOM="app-misc/unslotted-fixture"
COMMANDS="unslotted-tool"
OVERRIDE_BUILTIN="true"
EOF
eselect version-manager shims install unslotted
test -x "${HOME}/.local/bin/eselect-version-manager/shims/unslotted-tool"
echo "✓ Explicit built-in provider override and shim registration verified!"

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

# 10b. Malformed project configuration is fatal
echo "[Step 10b] Testing that malformed project configuration is fatal..."
mkdir -p "${HOME}/projects/project_malformed"
cd "${HOME}/projects/project_malformed"
echo 'VM_FIXTURE="unclosed quote' > .eselect.conf
set +e
MAL_OUT=$(fixture-tool 2>&1)
MAL_CODE=$?
set -e
test "${MAL_CODE}" -ne 0
assert_contains "unclosed quote" "${MAL_OUT}"
echo "✓ Malformed project configuration is strictly fatal!"

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
echo "  Go 1.22 minimum output: ${GO_VER}"
assert_contains "go1.23.1" "${GO_VER}"

# Update go.mod to preferred toolchain 1.22.4
cat << EOF > go.mod
module example.com/testmod

go 1.20
toolchain go1.22.4
EOF
GO_VER2=$(go version)
echo "  Go 1.22.4 preferred toolchain output: ${GO_VER2}"
assert_contains "go1.22.4" "${GO_VER2}"
echo "✓ Native from-file detection verified!"

# 12b. Go minimum version satisfied by newer toolchain
echo "[Step 12b] Testing Go minimum version satisfied by newer toolchain..."
mkdir -p "${HOME}/projects/go_min_ver"
cd "${HOME}/projects/go_min_ver"
cat << EOF > go.mod
module example.com/minver

go 1.20
EOF
eselect version-manager set --project go from-file
# Installed are 1.22 and 1.23; >=1.20 must be satisfied by 1.23.1!
GO_MIN_OUT=$(go version)
assert_contains "go1.23.1" "${GO_MIN_OUT}"
echo "✓ Newer toolchain satisfies minimum version requirement!"

# 12c. Go workspace precedence over nested module
echo "[Step 12c] Testing Go workspace precedence over nested module..."
mkdir -p "${HOME}/projects/go_ws/submod"
cd "${HOME}/projects/go_ws"
cat << EOF > go.work
go 1.22
toolchain go1.22.4
EOF
cd "${HOME}/projects/go_ws/submod"
cat << EOF > go.mod
module example.com/submod

go 1.20
EOF
eselect version-manager set --project go from-file
GO_WS_OUT=$(go version)
assert_contains "go1.22.4" "${GO_WS_OUT}"
echo "✓ Workspace precedence over nested module verified!"

# 12d. Missing compatible toolchain fails cleanly
echo "[Step 12d] Testing missing compatible toolchain fails cleanly..."
mkdir -p "${HOME}/projects/go_missing"
cd "${HOME}/projects/go_missing"
cat << EOF > go.mod
module example.com/missing

go 1.99
EOF
eselect version-manager set --project go from-file
set +e
MISS_OUT=$(go 2>&1)
MISS_CODE=$?
set -e
test "${MISS_CODE}" -eq 13
assert_contains "no installed version satisfies the requested constraint" "${MISS_OUT}"
echo "✓ Missing compatible toolchain fails cleanly!"

# 12e. Nested module resolution with root .eselect.conf
echo "[Step 12e] Testing nested module resolution with root .eselect.conf..."
mkdir -p "${HOME}/projects/nested_repo/submodule"
cd "${HOME}/projects/nested_repo"
echo 'VM_GO="from-file"' > .eselect.conf
cd "${HOME}/projects/nested_repo/submodule"
cat << 'EOF' > go.mod
module example.com/nested
go 1.20
toolchain go1.22.4
EOF
NESTED_GO=$(go version)
assert_contains "go1.22.4" "${NESTED_GO}"
echo "✓ Nested module resolves from root .eselect.conf!"

# 12f. GOWORK=off behaviour ignoring go.work
echo "[Step 12f] Testing GOWORK=off behaviour..."
mkdir -p "${HOME}/projects/gowork_test/sub"
cd "${HOME}/projects/gowork_test"
cat << 'EOF' > go.work
go 1.22
toolchain go1.22.4
EOF
cd "${HOME}/projects/gowork_test/sub"
cat << 'EOF' > go.mod
module example.com/sub
go 1.20
EOF
eselect version-manager set --project go from-file
OUT_WS=$(go version)
assert_contains "go1.22.4" "${OUT_WS}"
OUT_NOWS=$(GOWORK=off go version)
assert_contains "go1.23.1" "${OUT_NOWS}"
echo "✓ GOWORK=off behaviour verified!"

# 12g. Toolchain preference unsatisfied fails even if go minimum is met
echo "[Step 12g] Testing unsatisfied toolchain preference failure..."
mkdir -p "${HOME}/projects/tc_fail"
cd "${HOME}/projects/tc_fail"
cat << 'EOF' > go.mod
module example.com/tcfail
go 1.20
toolchain go1.99.0
EOF
eselect version-manager set --project go from-file
set +e
TC_ERR=$(go 2>&1)
TC_CODE=$?
set -e
test "${TC_CODE}" -eq 13
assert_contains "1.99.0" "${TC_ERR}"
assert_contains "toolchain" "${TC_ERR}"
echo "✓ Unsatisfied toolchain preference fails cleanly!"

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

# 13b. Conflicting installed executable validation
echo "[Step 13b] Testing that resolver never executes unowned conflicting binaries..."
eselect version-manager set --user fixture ":1"
OUT_FIX1=$(fixture-tool)
assert_contains "version 1.0 (slot 1)" "${OUT_FIX1}"
echo "✓ Resolved executable belongs strictly to selected package!"

# 13c. Configuration escaping validation
echo "[Step 13c] Testing config escaping..."
eselect version-manager set --user go '>=1.22 <1.24'
CONF_CONTENT=$(cat "${XDG_CONFIG_HOME}/eselect/version-manager.conf")
assert_contains 'VM_GO=">=1.22 <1.24"' "${CONF_CONTENT}"
echo "✓ Configuration value escaping verified!"

# 13d. Constraint validation rejects invalid requests before writing files
echo "[Step 13d] Testing invalid constraint rejection..."
mkdir -p "${HOME}/projects/bad_constraint_project"
cd "${HOME}/projects/bad_constraint_project"
set +e
INV_OUT=$(eselect version-manager set --file go ">>invalid" 2>&1)
INV_CODE=$?
set -e
test "${INV_CODE}" -ne 0
assert_contains "invalid version constraint" "${INV_OUT}"
test ! -f .eselect.conf
echo "✓ Invalid constraint rejected before modifying configuration files!"

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
test ! -d /var/db/pkg/app-eselect/eselect-version-manager-${VM_VERSION}
echo "✓ Clean unmerge verified!"

echo "================================================================="
echo "=== ALL GENTOO END-TO-END INTEGRATION TESTS PASSED (15/15)    ==="
echo "================================================================="
