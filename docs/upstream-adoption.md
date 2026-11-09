# Upstream Adoption Guide for Gentoo Maintainers

`eselect-version-manager` is designed to work with existing Gentoo packages out of the box without requiring ebuild maintainers to add special registration metadata.

## Recommended Ebuild Conventions for Co-installable Packages

To make a toolchain package seamlessly co-installable and selectable across multiple versions:

### 1. Slotted Installation
Use Portage slots for major/minor version series:
```bash
# In dev-lang/example-1.22.0.ebuild
SLOT="1.22"
```

### 2. Isolated Runtime Directories
Install runtime libraries and internals into version-specific directories rather than overwriting global `/usr/lib`:
```bash
# Ebuild layout
/usr/lib/example-1.22/bin/example
/usr/lib/example-1.22/lib/...
```

### 3. Slotted Binary Symlinks
Provide slotted symlinks in `/usr/bin`:
```bash
dosym "../lib/example-${SLOT}/bin/example" "/usr/bin/example-${SLOT}"
```

`eselect-version-manager` automatically inspects `CONTENTS` from `/var/db/pkg` and discovers versioned binaries (`example-1.22`, `example1.22`, etc.) and internal binary directories (`/usr/lib/example/1.22/bin/example`).

## No Proprietary Registration Files

Maintainers do **not** need to install:
- JSON or YAML manifest files
- Custom registration scripts
- Post-install hooks

Portage's standard `/var/db/pkg` database provides all required metadata (version, revision, slot, subslot, and installed file paths).
