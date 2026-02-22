# SSHaMan Revamp — Master Plan

> **Status**: Planning  
> **Created**: 2026-02-22  
> **Goal**: Transform SSHaMan from a custom JSON-based config manager into a proper SSH config management tool backed by native `~/.ssh/config` and `~/.ssh/config.d/*`, with a unified backend shared by both CLI and TUI.

---

## Why This Revamp?

1. **Reinventing the wheel**: The current system stores SSH configs as JSON files inside `~/.config/sshaman/`. OpenSSH already has a well-defined config format (`~/.ssh/config`) and a modular include system (`Include ~/.ssh/config.d/*`). We should use what already works.
2. **CLI/TUI divergence**: The TUI has its own config-reading logic (`tui/ssh_connections/ssh_connect.py`) that duplicates and diverges from the backend (`management/sshman.py`). Changes to one don't propagate to the other.
3. **Bugs and incomplete features**: Numerous issues (see `02-code-review.md`) including dead code, passwords stored in config, broken command chaining, and missing TUI management features.

---

## Plan Documents

| Document | Description |
|---|---|
| [01-backend-migration.md](01-backend-migration.md) | Replace JSON/filesystem config with native SSH config parsing and `config.d` support |
| [02-code-review.md](02-code-review.md) | Thorough code review: bugs, technical debt, inconsistencies |
| [03-cli-revamp.md](03-cli-revamp.md) | Redesign the CLI commands and align them with the new backend |
| [04-tui-revamp.md](04-tui-revamp.md) | Rewrite the TUI to use the backend and add config management features |
| [05-testing-strategy.md](05-testing-strategy.md) | Testing plan: fixtures, coverage targets, CI |
| [06-migration-guide.md](06-migration-guide.md) | How to migrate existing users from `~/.config/sshaman/` to `~/.ssh/config.d/` |

---

## High-Level Phases

### Phase 1: New Backend (`backend/`)
- Create Pydantic model for SSH `Host` blocks
- Build SSH config parser/writer (read and write `~/.ssh/config` and `config.d/*` files)
- Build `manager.py` with high-level operations: list, add, edit, remove, search hosts
- Ensure `~/.ssh/config` has `Include ~/.ssh/config.d/*` (add if missing, never overwrite)
- Unit tests using `tmp_path` — no real filesystem side effects

### Phase 2: CLI Revamp
- Rewrite CLI commands to call the new backend
- Add missing commands: `edit`, `remove`, `search`, `connect`, `show`
- Add `config-files` subcommand group to manage `config.d` files (create, list, delete)
- Remove old `configs/`, `entities/`, `management/` modules

### Phase 3: TUI Revamp
- Rewrite TUI to call the backend (not its own file-reading code)
- Replace the raw `DirectoryTree` with a host-list widget populated by the backend
- Add screens for: host list, host detail/edit, add host, manage config files
- Implement SSH/SFTP connect actions properly (no JSON parsing in TUI layer)
- Add key bindings for all management operations

### Phase 4: Testing & Polish
- Comprehensive test suite for backend, CLI, and TUI
- CI pipeline (GitHub Actions)
- Updated README with new usage instructions
- Migration tool for existing users

---

## Architecture Diagram

```
┌─────────────┐     ┌─────────────┐
│   CLI       │     │   TUI       │
│  (Click)    │     │  (Textual)  │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └───────┬───────────┘
               │
        ┌──────▼──────┐
        │   Backend    │
        │  manager.py  │
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ ssh_config.py│  ← Reads/writes ~/.ssh/config and config.d/*
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ host_entry.py│  ← Pydantic model for Host blocks
        └─────────────┘
```

Both CLI and TUI call `manager.py` → which calls `ssh_config.py` → which reads/writes native SSH config files. **No JSON. No `~/.config/sshaman/`.**
