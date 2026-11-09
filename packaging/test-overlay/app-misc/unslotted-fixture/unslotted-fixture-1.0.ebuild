# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DESCRIPTION="Test unslotted fixture package"
HOMEPAGE="https://github.com/arran4/eselect-version-manager"
SRC_URI=""

LICENSE="GPL-2+"
SLOT="0"
KEYWORDS="~amd64 ~arm64 ~x86"
IUSE=""

S="${WORKDIR}"

src_install() {
	exeinto "/usr/bin"
	cat << 'EOF' > unslotted-tool
#!/usr/bin/env bash
echo "unslotted-tool version 1.0 (unslotted)"
if [[ -n "$*" ]]; then
    echo "args: $*"
fi
EOF
	chmod +x unslotted-tool
	doexe unslotted-tool
}
