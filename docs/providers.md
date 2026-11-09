# Generic Provider Architecture

`eselect-version-manager` connects tools to Portage packages through a generic internal model:

```text
Tool Name
   ↓
Portage Package Provider
   ↓
Installed Matching Package Version
   ↓
Executable Path
   ↓
Required Runtime Environment
```

## Built-in Providers

### 1. Go Provider (`go`)
- **Package Atom:** `dev-lang/go`
- **Exposed Commands:** `go`, `gofmt`
- **Environment Injected:**
  - `GOTOOLCHAIN=local`: Enforces Gentoo Portage management by strictly preventing unauthorized network toolchain downloads.
  - `GOROOT`: Configured to the package's specific root directory (e.g. `/usr/lib/go/1.22`).
- **Native Version Detection (`from-file`):**
  - Search order: respects workspace precedence (`go.work` in current directory or any ancestor overrides module-level `go.mod`).
  - Supports nested modules when no `go.work` is present.
  - `go <version>`: specifies minimum required version (`>= <version>`), allowing newer installed toolchains to satisfy requirements.
  - `toolchain <version>`: specifies preferred toolchain (`toolchain go1.22.4`); if installed, the preferred version is selected; if missing, falls back to newer installed toolchains (`>= 1.22.4`). Missing compatible toolchains fail cleanly with exit code 13.
- **Executable Validation:** Validates that candidate binaries belong strictly to the selected package's `CONTENTS` or slot directories, preventing accidental execution of conflicting versions in `/usr/bin`.

### 2. Test Fixture Provider (`fixture`)
- **Package Atom:** `app-misc/version-manager-fixture`
- **Exposed Commands:** `fixture-tool`, `fixture-helper`
- **Slotted Co-Installation:** Demonstrates multi-binary co-installable toolchain slots (`SLOT="1"` and `SLOT="2"`).
- **Environment Injected:** `VM_FIXTURE_HOME`, `VM_FIXTURE_SLOT`.

### 3. Unslotted Fixture Provider (`unslotted`)
- **Package Atom:** `app-misc/unslotted-fixture`
- **Exposed Commands:** `unslotted-tool`
- **Behavior:** Validates that unslotted packages (`SLOT="0"`) function seamlessly alongside slotted toolchains.

## Dynamic Providers (`providers.d/`)

Users and administrators can add support for any Portage-managed package without modifying Python source code. Simply drop a declarative `.conf` file into either:
- System: `/etc/eselect/version-manager/providers.d/<tool>.conf` (respects `EROOT`)
- User: `${XDG_CONFIG_HOME:-~/.config}/eselect/version-manager/providers.d/<tool>.conf`

### Provider Configuration Format

```bash
# /etc/eselect/version-manager/providers.d/python.conf
PACKAGE_ATOM="dev-lang/python"
COMMANDS="python python3"
```

```bash
# ~/.config/eselect/version-manager/providers.d/rust.conf
PACKAGE_ATOM="dev-lang/rust-bin"
COMMANDS="rustc cargo rustfmt"
```

Once defined, shims can be installed via `eselect version-manager shims install <tool>`, and version constraints managed via `set`, `get`, and `list`.

## Implementing a Programmatic Provider

New built-in providers inherit from `BaseProvider`:

```python
from eselect_version_manager.providers.base import BaseProvider
from eselect_version_manager.models import InstalledPackage
from typing import List, Dict

class RustProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "rust"

    @property
    def package_atom(self) -> str:
        return "dev-lang/rust-bin"

    @property
    def commands(self) -> List[str]:
        return ["rustc", "cargo", "rustfmt", "rustdoc"]

    def get_environment(self, package: InstalledPackage, executable_path: str) -> Dict[str, str]:
        return {
            "RUSTC": executable_path,
        }
```
