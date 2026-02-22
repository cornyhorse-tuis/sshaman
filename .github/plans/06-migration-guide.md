# Phase 5: Migration Guide — JSON to SSH Config

> **Status**: Not started  
> **Depends on**: Phase 1 (Backend)

---

## Overview

Existing SSHaMan users have configs stored in `~/.config/sshaman/` as JSON files. We need to provide a one-time migration tool that converts these to native SSH config format in `~/.ssh/config.d/`.

---

## Current Format

```
~/.config/sshaman/
├── group1/
│   ├── vm1.json
│   │   {
│   │       "alias": "vm1",
│   │       "host": "192.168.1.100",
│   │       "port": 22,
│   │       "user": "root",
│   │       "identity_file": "~/.ssh/id_rsa",
│   │       "password": "12345",
│   │       "forward_ports": ["80:localhost:8080"],
│   │       "start_commands": ["echo hello"]
│   │   }
│   └── subgroup1/
│       └── vm2.json
└── group2/
```

## Target Format

```
~/.ssh/config.d/
└── sshaman-migrated
    Host vm1
        HostName 192.168.1.100
        User root
        Port 22
        IdentityFile ~/.ssh/id_rsa

    Host vm2
        HostName 192.168.1.100
        User root
        Port 22
        IdentityFile ~/.ssh/id_rsa
```

---

## Migration Rules

1. **Each JSON file** becomes a `Host` block in `~/.ssh/config.d/sshaman-migrated`
2. **`alias`** → `Host` directive name
3. **`host`** → `HostName` directive
4. **`user`** → `User` directive
5. **`port`** → `Port` directive (omit if 22)
6. **`identity_file`** → `IdentityFile` directive
7. **`password`** → **DROPPED** (log a warning: "Password-based auth is not supported; please use SSH keys")
8. **`forward_ports`** → `LocalForward` directives (one per entry)
9. **`start_commands`** → **DROPPED** (log a warning: "RemoteCommand can be used, but start_commands are not migrated automatically")
10. **`server_group_path`** → **DROPPED** (internal field)
11. **Group hierarchy** → Optionally add comments: `# Group: group1/subgroup1`
12. **Duplicate aliases** → rename to `alias-2`, `alias-3`, etc. with a warning

---

## CLI Command

```
sshaman migrate [--source PATH] [--config-file NAME] [--dry-run]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source` | `~/.config/sshaman/` | Path to old SSHaMan config directory |
| `--config-file` | `sshaman-migrated` | Name of config.d file to create |
| `--dry-run` | off | Show what would be migrated without writing |

### Output example (dry run)

```
SSHaMan Migration — Dry Run
============================

Found 5 hosts in ~/.config/sshaman/

  ✓ vm1 (group1/) → Host vm1
  ✓ vm2 (group1/subgroup1/) → Host vm2
  ⚠ vm3 (group1/) → Host vm3
      Warning: password field will be dropped
  ⚠ vm4 (group2/) → Host vm4
      Warning: start_commands will not be migrated
  ✓ vm5 (group2/) → Host vm5

Would write 5 hosts to ~/.ssh/config.d/sshaman-migrated
Run without --dry-run to apply.
```

---

## Implementation

```python
# In backend/migrate.py (temporary module, can be removed after migration period)

import json
from pathlib import Path
from backend.host_entry import HostEntry
from backend.ssh_config import SSHConfigManager

def discover_json_configs(source: Path) -> list[tuple[Path, dict]]:
    """Walk the source directory and find all .json config files."""
    configs = []
    for json_file in source.rglob("*.json"):
        with json_file.open() as f:
            data = json.load(f)
            configs.append((json_file, data))
    return configs

def convert_json_to_host_entry(json_path: Path, data: dict, source_root: Path) -> tuple[HostEntry, list[str]]:
    """Convert a JSON config dict to a HostEntry, returning warnings."""
    warnings = []
    
    if data.get("password"):
        warnings.append(f"Password for '{data['alias']}' will be dropped. Use SSH keys instead.")
    
    if data.get("start_commands"):
        warnings.append(f"start_commands for '{data['alias']}' will not be migrated.")
    
    # Compute group path for comment
    rel = json_path.parent.relative_to(source_root)
    comment = f"Migrated from {rel}/" if str(rel) != "." else "Migrated by SSHaMan"
    
    local_forwards = []
    for fp in (data.get("forward_ports") or []):
        if fp:  # skip empty strings
            local_forwards.append(fp)
    
    entry = HostEntry(
        name=data["alias"],
        hostname=data["host"],
        user=data.get("user"),
        port=data.get("port", 22),
        identity_file=Path(data["identity_file"]) if data.get("identity_file") else None,
        local_forwards=local_forwards,
        comment=comment,
    )
    
    return entry, warnings

def migrate(source: Path, config_manager: SSHConfigManager, 
            config_file: str = "sshaman-migrated", dry_run: bool = False) -> dict:
    """Run the migration. Returns summary dict."""
    ...
```

---

## Safety Measures

1. **Never delete the source directory** — the user does that manually after verifying
2. **Never overwrite existing config.d files** — if `sshaman-migrated` exists, error out unless `--force`
3. **Backup `~/.ssh/config`** before adding Include directive
4. **Validate all generated config** — parse it back to make sure it round-trips correctly
5. **Set correct permissions** — `0o600` for config files, `0o700` for directories

---

## Tasks

- [ ] Implement `backend/migrate.py`
- [ ] Add `sshaman migrate` CLI command
- [ ] Write tests for migration (various JSON configs, edge cases)
- [ ] Handle duplicate host aliases
- [ ] Handle missing/malformed JSON files gracefully
- [ ] Log warnings for dropped fields (password, start_commands)
- [ ] Document migration instructions in README
