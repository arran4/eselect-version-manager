# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DESCRIPTION="Test fixture toolchain package slot 1"
HOMEPAGE="https://github.com/arran4/eselect-version-manager"
SRC_URI=""

LICENSE="GPL-2+"
SLOT="1"
KEYWORDS="~amd64 ~arm64 ~x86"
IUSE=""

S="${WORKDIR}"

src_install() {
	# Install into slot-specific lib directory
	exeinto "/usr/lib/vm-fixture-${SLOT}/bin"
	
	cat << 'EOF' > fixture-tool
#!/usr/bin/env bash
echo "fixture-tool version 1.0 (slot 1) [ENV_HOME=${VM_FIXTURE_HOME}]"
if [[ -n "$*" ]]; then
    echo "args: $*"
fi
EOF
	chmod +x fixture-tool
	doexe fixture-tool

	cat << 'EOF' > fixture-helper
#!/usr/bin/env bash
echo "fixture-helper version 1.0 (slot 1)"
EOF
	chmod +x fixture-helper
	doexe fixture-helper

	# Provide versioned binary in /usr/bin
	dosym "../lib/vm-fixture-${SLOT}/bin/fixture-tool" "/usr/bin/fixture-tool-${SLOT}"
	dosym "../lib/vm-fixture-${SLOT}/bin/fixture-helper" "/usr/bin/fixture-helper-${SLOT}"
}
