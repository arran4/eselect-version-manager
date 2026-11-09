# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DESCRIPTION="Mocked Go toolchain package for fast testing"
HOMEPAGE="https://golang.org/"
SRC_URI=""

LICENSE="BSD"
SLOT="1.22"
KEYWORDS="~amd64 ~arm64 ~x86"
IUSE=""

S="${WORKDIR}"

src_install() {
	# Install into /usr/lib/go/${SLOT}/bin
	exeinto "/usr/lib/go/${SLOT}/bin"

	cat << 'EOF' > go
#!/usr/bin/env bash
if [[ "$1" == "version" ]]; then
    echo "go version go1.22.4 linux/amd64"
    exit 0
elif [[ "$1" == "env" && "$2" == "GOROOT" ]]; then
    echo "${GOROOT:-/usr/lib/go/1.22}"
    exit 0
fi
echo "go1.22.4 invoked with: $*"
EOF
	chmod +x go
	doexe go

	cat << 'EOF' > gofmt
#!/usr/bin/env bash
echo "gofmt go1.22.4"
EOF
	chmod +x gofmt
	doexe gofmt

	# Versioned binaries in /usr/bin
	dosym "../lib/go/${SLOT}/bin/go" "/usr/bin/go-${SLOT}"
	dosym "../lib/go/${SLOT}/bin/gofmt" "/usr/bin/gofmt-${SLOT}"
}
