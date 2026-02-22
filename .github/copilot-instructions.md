# Copilot Instructions for SSHaMan

## Project Overview

SSHaMan (SSH Manager) is a Python CLI/TUI tool for managing SSH connections and configurations. It currently uses a custom JSON-based config store in `~/.config/sshaman/` but is being migrated to use the native `~/.ssh/config` and `~/.ssh/config.d/*` pattern.

## Architecture Goals

- **Single backend**: All SSH config management logic lives in `management/sshman.py` (the "backend"). Both the CLI (`cli/sshaman_cli.py`) and TUI (`tui/`) must call the same backend — the TUI should never implement its own config reading/writing logic.
- **Native SSH config**: Use `~/.ssh/config` with `Include ~/.ssh/config.d/*` instead of the custom `~/.config/sshaman/` JSON store. Configs are standard OpenSSH `Host` blocks.
- **config.d pattern**: Users can create named config files in `~/.ssh/config.d/` (e.g., `10-work-servers`, `20-home-lab`). The tool manages these files.

## Tech Stack

- **Python 3.10+**
- **Click** — CLI framework
- **Textual** — TUI framework
- **Pydantic** — data models / validation
- **Rich** — terminal formatting (used by Textual)
- **pytest** — testing

## Code Conventions

- Use type hints everywhere.
- Use `pathlib.Path` instead of `os.path` for all path operations.
- Pydantic models for all data structures (Host entries, config file representations).
- No global mutable state — avoid `set_config_path()` patterns. Pass config paths explicitly.
- Never store passwords in config files; rely on SSH key-based auth or ssh-agent.
- All user-facing strings should be clear, consistent, and typo-free.
- Docstrings on all public functions (Google style).
- Keep modules focused: one responsibility per file.

## File Layout (Target)

```
sshaman/
├── __init__.py
├── entrypoint.py              # Entry point: CLI dispatch or TUI launch
├── cli/
│   ├── __init__.py
│   └── sshaman_cli.py         # Click CLI — calls backend
├── backend/
│   ├── __init__.py
│   ├── ssh_config.py           # Read/write/parse ~/.ssh/config and config.d files
│   ├── host_entry.py           # Pydantic model for a Host block
│   └── manager.py              # High-level operations (add, remove, list, edit hosts)
├── tui/
│   ├── __init__.py
│   ├── app.py                  # Textual App (replaces tree.py)
│   ├── screens/                # Textual screens (list, edit, add, connect)
│   ├── widgets/                # Custom Textual widgets
│   └── app.tcss                # Stylesheet
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── test_backend.py
│   ├── test_cli.py
│   └── test_tui.py
└── requirements.txt
```

## Testing

- Use `tmp_path` pytest fixtures — never write to real `~/.ssh/` in tests.
- Mock SSH connections; never actually connect in unit tests.
- Tests must be runnable with `pytest` from the repo root.
- **Target ~100% test coverage.** Every module should have thorough unit tests. Use `pytest-cov` with `--cov-fail-under=95`.
- CLI tests use Click's `CliRunner`; TUI tests use Textual's `pilot`.
- Write unit tests for all backend logic, CLI commands, and TUI screen behavior.

### `# pragma: no cover`

Use `# pragma: no cover` **only** for code that genuinely cannot or should not be unit tested:
- **`os.execvp()` calls** — these replace the process and can't return in a test.
- **`if __name__ == "__main__"` blocks** — entry point guards.
- **Defensive branches that are unreachable in practice** but exist for safety (e.g., a fallback `else` after exhaustive type checks).
- **Platform-specific code paths** that can't run in CI (e.g., macOS Keychain integration).

Do **not** use `# pragma: no cover` to skip:
- Error handling — test that exceptions are raised correctly.
- Edge cases — write tests for them.
- Complex logic you don't want to bother testing — simplify it or test it.

Every use of `# pragma: no cover` should have a brief comment explaining why:
```python
os.execvp("ssh", args)  # pragma: no cover — replaces process, untestable
```

## SSH Config Format Reference

Standard OpenSSH config block:
```
Host my-server
    HostName 192.168.1.100
    User matt
    Port 22
    IdentityFile ~/.ssh/id_rsa
    IgnoreUnknown UseKeychain
    UseKeychain yes
```

The main `~/.ssh/config` should include:
```
Include ~/.ssh/config.d/*
```

## Important Warnings

- **Never overwrite `~/.ssh/config` without backing it up first.** Always append or manage only the `Include` directive.
- **Preserve comments and formatting** in existing SSH config files when editing.
- **File permissions matter**: SSH config files must be `600`, directories `700`.
- **Do not store sensitive data** (passwords, private keys) in the application's own config or state files.

## Current Bugs / Technical Debt (see .github/plans/)

Refer to the plan documents in `.github/plans/` for the full revamp roadmap and known issues.
