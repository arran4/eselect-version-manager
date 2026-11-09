# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

PYTHON_COMPAT=( python3_{11..14} )

inherit python-single-r1

DESCRIPTION="Gentoo-native project-aware toolchain version manager"
HOMEPAGE="https://github.com/arran4/eselect-version-manager"
SRC_URI=""

LICENSE="GPL-2+"
SLOT="0"
KEYWORDS="~amd64 ~arm64 ~x86"
IUSE=""

REQUIRED_USE="${PYTHON_REQUIRED_USE}"

DEPEND="
	app-admin/eselect
	sys-apps/portage
"
RDEPEND="
	${DEPEND}
	${PYTHON_DEPS}
"
BDEPEND="
	${PYTHON_DEPS}
"

S="${WORKDIR}/${P}"

src_unpack() {
	mkdir -p "${S}" || die
	if [[ -d "/workspace/eselect_version_manager" ]]; then
		cp -r /workspace/bin /workspace/config /workspace/docs /workspace/eselect_version_manager \
			/workspace/modules /workspace/README.md "${S}/" || die
	fi
}

src_install() {
	# Install eselect module
	insinto /usr/share/eselect/modules
	doins "${S}/modules/version-manager.eselect"

	# Install Python package
	python_domodule "${S}/eselect_version_manager"

	# Install dispatcher executable
	exeinto /usr/libexec/eselect-version-manager
	newexe "${S}/bin/dispatcher" dispatcher
	python_fix_shebang "${ED}/usr/libexec/eselect-version-manager/dispatcher"

	# Symlink for direct CLI invocation
	dosym ../libexec/eselect-version-manager/dispatcher /usr/bin/eselect-version-manager

	# Install default system configuration
	insinto /etc/eselect
	doins "${S}/config/version-manager.conf"

	# Install documentation
	dodoc "${S}/README.md"
	if [[ -d "${S}/docs" ]]; then
		dodoc "${S}/docs"/*.md
	fi
}
