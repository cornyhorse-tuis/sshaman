# Phase 1: Backend Migration — JSON to Native SSH Config

> **Status**: Not started  
> **Depends on**: Nothing (this is the foundation)  
> **Blocks**: Phases 2, 3, 4

---

## Overview

Replace the entire custom config system (`~/.config/sshaman/` with JSON files in nested directories) with native OpenSSH config format using `~/.ssh/config` and `~/.ssh/config.d/*`.

---

## What Exists Today

### Current storage model
```
~/.config/sshaman/
├── group1/
│   ├── vm1.json          ← {"alias":"vm1","host":"192.168.1.100","port":22,...}
│   ├── vm2.json
│   └── subgroup1/
│       └── subgroup2/
└── group2/
```

### Current code modules to replace
| Module | Role | Problem |
|---|---|---|
| `configs/path.py` | Global mutable `CONFIG_PATH` | Uses `os.path`, global state via `set_config_path()` |
| `entities/server.py` | Pydantic `Server` model | Stores `password` field, serializes to JSON, uses `os.path` |
| `entities/server_group.py` | Pydantic `ServerGroup` model | Creates directories on `__init__`, uses global config path |
| `management/sshman.py` | `SSHAMan` class | Walks filesystem, reads JSON, creates dirs/groups |
| `tui/ssh_connections/ssh_connect.py` | Builds SSH commands from JSON | Duplicates backend logic, reads JSON directly |

---

## Target Storage Model

```
~/.ssh/
├── config                    ← Must contain: Include ~/.ssh/config.d/*
└── config.d/
    ├── 10-work-servers       ← Standard SSH config blocks
    ├── 20-home-lab
    └── 30-cloud
```

Example `config.d/10-work-servers`:
```
# Managed by SSHaMan
Host web-prod
    HostName 10.0.1.50
    User deploy
    Port 22
    IdentityFile ~/.ssh/work_key

Host db-prod
    HostName 10.0.1.51
    User admin
    Port 2222
    IdentityFile ~/.ssh/work_key
```

---

## New Modules to Create

### `backend/__init__.py`
Empty or re-exports.

### `backend/host_entry.py` — Pydantic Model

```python
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional

class HostEntry(BaseModel):
    """Represents a single SSH Host block."""
    name: str                                    # The Host alias (e.g., "web-prod")
    hostname: str                                # HostName directive
    user: Optional[str] = None
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: Optional[Path] = None
    proxy_jump: Optional[str] = None
    forward_agent: Optional[bool] = None
    local_forwards: list[str] = Field(default_factory=list)   # -L equivalents
    remote_forwards: list[str] = Field(default_factory=list)  # -R equivalents
    extra_options: dict[str, str] = Field(default_factory=dict)  # Catch-all for any SSH option
    source_file: Optional[Path] = None           # Which config.d file this came from
    comment: Optional[str] = None                # Comment above the Host block

    def to_ssh_config(self) -> str:
        """Serialize to SSH config block text."""
        ...

    @classmethod
    def from_ssh_config(cls, block: str, source_file: Path | None = None) -> "HostEntry":
        """Parse a Host block string into a HostEntry."""
        ...
```

**Key design decisions**:
- No `password` field — SSH key auth or ssh-agent only.
- No `start_commands` — out of scope for SSH config (could be a separate feature later).
- `extra_options` dict captures any SSH option we don't explicitly model.
- `source_file` tracks provenance for editing/removing.

### `backend/ssh_config.py` — Config File I/O

Responsibilities:
1. **Read** `~/.ssh/config` and all files in `~/.ssh/config.d/`
2. **Parse** Host blocks into `HostEntry` objects
3. **Write** Host blocks back to specific `config.d` files
4. **Ensure** `~/.ssh/config` contains `Include ~/.ssh/config.d/*`
5. **Manage** `config.d` files (create, list, delete, rename)
6. **Preserve** comments and formatting in files we didn't create
7. **Set permissions**: files `0o600`, directories `0o700`

```python
from pathlib import Path

class SSHConfigManager:
    """Low-level SSH config file operations."""

    def __init__(self, ssh_dir: Path | None = None):
        self.ssh_dir = ssh_dir or Path.home() / ".ssh"
        self.config_file = self.ssh_dir / "config"
        self.config_d = self.ssh_dir / "config.d"

    def ensure_config_d_setup(self) -> None:
        """Create config.d dir and add Include directive if missing."""
        ...

    def list_config_files(self) -> list[Path]:
        """List all files in config.d/."""
        ...

    def read_all_hosts(self) -> list[HostEntry]:
        """Parse all Host blocks from config and config.d."""
        ...

    def read_hosts_from_file(self, path: Path) -> list[HostEntry]:
        """Parse Host blocks from a single file."""
        ...

    def write_host(self, entry: HostEntry, config_file: str) -> None:
        """Append a Host block to a config.d file."""
        ...

    def remove_host(self, host_name: str) -> None:
        """Remove a Host block by name from its source file."""
        ...

    def update_host(self, host_name: str, entry: HostEntry) -> None:
        """Update an existing Host block in-place."""
        ...

    def create_config_file(self, name: str) -> Path:
        """Create a new empty config.d file with correct permissions."""
        ...

    def delete_config_file(self, name: str) -> None:
        """Delete a config.d file (after confirmation)."""
        ...
```

### `backend/manager.py` — High-Level Operations

This is the **single API** that both CLI and TUI call:

```python
class SSHManager:
    """High-level SSH config management operations."""

    def __init__(self, ssh_dir: Path | None = None):
        self.config = SSHConfigManager(ssh_dir)

    def list_hosts(self, filter: str | None = None) -> list[HostEntry]:
        """List all hosts, optionally filtered by name/hostname pattern."""
        ...

    def get_host(self, name: str) -> HostEntry | None:
        """Get a single host by name."""
        ...

    def add_host(self, entry: HostEntry, config_file: str = "sshaman-hosts") -> None:
        """Add a new host entry."""
        ...

    def edit_host(self, name: str, **updates) -> HostEntry:
        """Edit fields on an existing host."""
        ...

    def remove_host(self, name: str) -> None:
        """Remove a host."""
        ...

    def connect_command(self, name: str) -> str:
        """Build an SSH command string for a host."""
        ...

    def sftp_command(self, name: str) -> str:
        """Build an SFTP command string for a host."""
        ...

    def list_config_files(self) -> list[Path]:
        ...

    def create_config_file(self, name: str) -> Path:
        ...

    def delete_config_file(self, name: str) -> None:
        ...
```

---

## Modules to Delete (after migration)

- `configs/` (entire directory)
- `entities/` (entire directory)
- `management/` (entire directory)
- `tui/ssh_connections/ssh_connect.py` (SSH command building moves to backend)
- `tui/file_operations/new_file.py` (add-host moves to backend)

---

## SSH Config Parsing Notes

### Parsing strategy
- Read file line by line
- Track current `Host` block (starts with `Host <name>`, ends at next `Host` or EOF)
- Each indented line within a block is a `Key Value` directive
- Preserve comment lines (lines starting with `#`)
- Handle `Match` blocks by ignoring them (we only manage `Host` blocks)

### Edge cases to handle
- Multiple `Host` aliases on one line: `Host foo bar` (treat as one entry with name "foo bar")
- Wildcard hosts: `Host *` (read-only, never modify)
- `Match` blocks (skip/preserve)
- Blank lines between blocks
- Comments interspersed with directives
- Files with no Host blocks (just global options)

---

## Tasks

- [ ] Create `backend/` package with `__init__.py`
- [ ] Implement `backend/host_entry.py` with Pydantic model and serialization
- [ ] Implement `backend/ssh_config.py` with config file I/O
- [ ] Implement `backend/manager.py` with high-level operations
- [ ] Write comprehensive tests in `tests/test_backend/` (target 100% coverage)
- [ ] Create a `conftest.py` with `tmp_path`-based fixtures (fake `~/.ssh/` directory)
- [ ] Test parsing of real-world SSH config files (various edge cases)
- [ ] Test writing and round-tripping (parse → serialize → parse = same result)
- [ ] Test `config.d` file management (create, list, delete)
- [ ] Test permission setting on created files
- [ ] Test every error path (missing files, bad permissions, malformed config blocks)
- [ ] Test boundary values (port 1, port 65535, empty hostname, very long host names)
- [ ] Ensure 100% line + branch coverage on all backend modules
- [ ] Use `# pragma: no cover` only where truly untestable (document each use)
