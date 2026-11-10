# syntax=docker/dockerfile:1.7
# One Portage installation path for CI, demonstration images and releases.
# Pin upstream Gentoo images to reviewed OCI digests; update intentionally.
FROM gentoo/portage@sha256:84e5a31feb6302cde18f904d16c877eccbbdc3943853d22965145ae8154491a9 AS gentoo-repository

FROM gentoo/stage3@sha256:74bd9b8e57bdf72d88ccacc4c467b8e73af584b06c3e89b581db8d35930416d3 AS installed

ARG VM_VERSION=0.1.0
ARG VM_SOURCE=checkout

LABEL org.opencontainers.image.source="https://github.com/arran4/eselect-version-manager" \
      org.opencontainers.image.description="Gentoo eselect version manager with Portage-backed tool selection" \
      org.opencontainers.image.licenses="GPL-2.0-or-later"

# Use the exact same Gentoo package repository snapshot as the prior
# volume-mounted container integration suite, but in a cacheable layer.
COPY --from=gentoo-repository /var/db/repos/gentoo /var/db/repos/gentoo

WORKDIR /workspace
COPY overlay/ /workspace/overlay/
COPY bin/ /workspace/bin/
COPY config/ /workspace/config/
COPY docs/ /workspace/docs/
COPY eselect_version_manager/ /workspace/eselect_version_manager/
COPY modules/ /workspace/modules/
COPY README.md /workspace/README.md

RUN set -eu; \
    mkdir -p /etc/portage/repos.conf /etc/portage/package.accept_keywords /var/cache/distfiles; \
    printf '[eselect-version-manager-overlay]\nlocation = /workspace/overlay\npriority = 100\nauto-sync = false\n' > /etc/portage/repos.conf/eselect-version-manager.conf; \
    printf 'app-eselect/eselect-version-manager ~amd64\n' > /etc/portage/package.accept_keywords/eselect-version-manager; \
    if [ ! -e /etc/portage/make.profile ]; then \
      ln -s /var/db/repos/gentoo/profiles/default/linux/amd64/23.0 /etc/portage/make.profile; \
    fi; \
    printf 'FEATURES="-ipc-sandbox -network-sandbox -pid-sandbox"\n' >> /etc/portage/make.conf; \
    pkg="/workspace/overlay/app-eselect/eselect-version-manager/eselect-version-manager-${VM_VERSION}.ebuild"; \
    if [ ! -f "${pkg}" ]; then \
      echo "Missing overlay ebuild for v${VM_VERSION}; update the companion overlay before release" >&2; \
      exit 2; \
    fi; \
    case "${VM_SOURCE}" in \
      checkout) \
        tar -czf "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz" \
          --transform="s,^,eselect-version-manager-${VM_VERSION}/," \
          -C /workspace bin config docs eselect_version_manager modules README.md; \
        chown portage:portage "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz"; \
        chmod 0644 "/var/cache/distfiles/eselect-version-manager-${VM_VERSION}.tar.gz" \
        ;; \
      release) \
        echo "Fetching the tagged upstream source archive through Portage" \
        ;; \
      *) echo "VM_SOURCE must be checkout or release" >&2; exit 2 ;; \
    esac; \
    ebuild --force "${pkg}" manifest; \
    emerge --quiet-build=y --oneshot "app-eselect/eselect-version-manager"; \
    test -x /usr/libexec/eselect-version-manager/dispatcher; \
    eselect version-manager help >/dev/null

# CI target: run all real Gentoo container tests against the same installed
# package/Portage repository used by the demo image. Never publish this stage.
FROM installed AS e2e
COPY scripts/ /workspace/scripts/
RUN set -eu; \
    rm -f /etc/portage/repos.conf/eselect-version-manager.conf; \
    bash /workspace/scripts/test_in_gentoo.sh

# Public demonstration image: real Portage-installed version manager, but the
# side-by-side fixture programs are intentionally synthetic and clearly named.
# It does NOT install the fake dev-lang/go packages from the CI-only overlay.
FROM installed AS demo
RUN set -eu; \
    printf '[eselect-version-manager-fixtures]\nlocation = /workspace/overlay/tests/portage-overlay\npriority = 110\nauto-sync = false\n' > /etc/portage/repos.conf/eselect-version-manager-fixtures.conf; \
    printf 'app-misc/version-manager-fixture ~amd64\n' > /etc/portage/package.accept_keywords/eselect-version-manager-fixtures; \
    emerge --quiet-build=y --oneshot \
      'app-misc/version-manager-fixture:1' \
      'app-misc/version-manager-fixture:2'; \
    # The build uses a pinned overlay snapshot; only interactive demos have
    # the Portage-native Git sync configuration for opt-in updates.
    if ! command -v git >/dev/null 2>&1; then \
      emerge --quiet-build=y --oneshot dev-vcs/git; \
    fi; \
    rm -f /etc/portage/repos.conf/eselect-version-manager.conf; \
    printf '[eselect-version-manager-overlay]\\nlocation = /var/db/repos/eselect-version-manager-overlay\\nsync-type = git\\nsync-uri = https://github.com/arran4/eselect-version-manager-overlay.git\\nauto-sync = yes\\nmasters = gentoo\\n' \
      > /etc/portage/repos.conf/eselect-version-manager-overlay.conf; \
    useradd -m -s /bin/bash demo; \
    mkdir -p /home/demo/projects/slot-1 /home/demo/projects/slot-2; \
    printf 'VM_FIXTURE=":1"\n' > /home/demo/projects/slot-1/.eselect.conf; \
    printf 'VM_FIXTURE=":2"\n' > /home/demo/projects/slot-2/.eselect.conf; \
    chown -R demo:demo /home/demo/projects
USER demo
RUN eselect version-manager shims install fixture python
ENV PATH="/home/demo/.local/bin/eselect-version-manager/shims:${PATH}"
WORKDIR /home/demo
CMD ["/bin/bash"]
