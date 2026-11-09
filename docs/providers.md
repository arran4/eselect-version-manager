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
  - Reads `go.work` (if present) or `go.mod`.
  - Supports `go <version>` (e.g. `go 1.22` -> `>=1.22`).
  - Supports `toolchain <version>` (e.g. `toolchain go1.22.4` -> `>=1.22.4`).

### 2. Test Fixture Provider (`fixture`)
- **Package Atom:** `app-misc/version-manager-fixture`
- **Exposed Commands:** `fixture-tool`, `fixture-helper`
- **Slotted Co-Installation:** Demonstrates multi-binary co-installable toolchain slots (`SLOT="1"` and `SLOT="2"`).
- **Environment Injected:** `VM_FIXTURE_HOME`, `VM_FIXTURE_SLOT`.

### 3. Unslotted Fixture Provider (`unslotted`)
- **Package Atom:** `app-misc/unslotted-fixture`
- **Exposed Commands:** `unslotted-tool`
- **Behavior:** Validates that unslotted packages (`SLOT="0"`) function seamlessly alongside slotted toolchains.

## Implementing a New Provider

New providers inherit from `BaseProvider`:

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
