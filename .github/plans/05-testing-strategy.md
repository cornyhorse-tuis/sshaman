# Phase 4: Testing Strategy

> **Status**: Not started  
> **Depends on**: Phases 1-3  
> **Can begin partially during**: Phase 1

---

## Overview

Build a comprehensive test suite targeting **~100% code coverage** that validates the backend, CLI, and TUI without touching real SSH configs or making real SSH connections. Use `# pragma: no cover` only for genuinely untestable code (process replacement, `__main__` guards) and always document the reason.

---

## Current Test Problems

1. **Tests write to real filesystem** (`~/.config/test_sshaman/`) instead of using `tmp_path`
2. **Global state pollution** — `set_config_path()` changes module-level global, leaks between tests
3. **Test data inconsistencies** — fixture creates `sg1` but tests expect `subgroup1`; `vm2` is added to wrong group
4. **`util_tests.print_diff`** crashes on list input (calls `.splitlines()` on a list)
5. **No TUI tests at all**
6. **Most CLI tests are commented out**
7. **`dev_test_sshaman.py`** is a manual dev script, not a proper test

---

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (tmp ssh dirs, sample configs)
├── test_backend/
│   ├── test_host_entry.py   # HostEntry model tests
│   ├── test_ssh_config.py   # SSH config parsing/writing tests
│   └── test_manager.py      # High-level operations tests
├── test_cli.py              # CLI command tests via CliRunner
└── test_tui.py              # TUI screen tests via Textual pilot
```

---

## Fixtures (`conftest.py`)

```python
import pytest
from pathlib import Path
from backend.manager import SSHManager

@pytest.fixture
def ssh_dir(tmp_path: Path) -> Path:
    """Create a temporary ~/.ssh/ equivalent with config.d/."""
    ssh = tmp_path / ".ssh"
    ssh.mkdir(mode=0o700)
    config_d = ssh / "config.d"
    config_d.mkdir(mode=0o700)
    
    # Write a base config with Include
    config = ssh / "config"
    config.write_text("Include ~/.ssh/config.d/*\n")  # Will need path fixup
    config.chmod(0o600)
    
    return ssh

@pytest.fixture
def sample_config(ssh_dir: Path) -> Path:
    """Create a sample config.d file with test hosts."""
    config_file = ssh_dir / "config.d" / "test-hosts"
    config_file.write_text(
        "# Test hosts\n"
        "Host web-server\n"
        "    HostName 192.168.1.100\n"
        "    User admin\n"
        "    Port 22\n"
        "    IdentityFile ~/.ssh/id_rsa\n"
        "\n"
        "Host db-server\n"
        "    HostName 192.168.1.101\n"
        "    User postgres\n"
        "    Port 5432\n"
        "\n"
    )
    config_file.chmod(0o600)
    return ssh_dir

@pytest.fixture
def manager(sample_config: Path) -> SSHManager:
    """Create an SSHManager pointed at the sample config."""
    return SSHManager(ssh_dir=sample_config)
```

**Key principle**: Every test gets its own `tmp_path`. No shared state. No global mutations. No real `~/.ssh/` access.

---

## Backend Tests

### `test_host_entry.py`
- Parse a single Host block → correct `HostEntry` fields
- Serialize a `HostEntry` → valid SSH config text
- Round-trip: parse → serialize → parse = identical object
- Validate port range (1-65535)
- Reject port 0 and port 65536
- Handle optional fields (missing User, missing IdentityFile)
- Handle `extra_options` for unknown SSH directives
- Reject invalid data (empty name, empty hostname)
- Test default values (port=22, empty lists for forwards)
- Test `source_file` and `comment` round-trip
- Test with all fields populated vs minimal fields
- **Target: 100% line + branch coverage**

### `test_ssh_config.py`
- Read a config.d file with multiple Host blocks
- Read config.d directory with multiple files
- Write a new Host block to an existing file
- Write a new Host block to a new file
- Remove a Host block from a file (preserving others)
- Remove the only Host block from a file
- Update a Host block in-place
- Preserve comments and blank lines when editing
- Create config.d directory and set permissions
- Ensure Include directive is added to main config
- Ensure Include directive is not duplicated if already present
- Handle empty files, files with only comments
- Handle wildcard `Host *` entries (read but don't modify)
- Handle missing `~/.ssh/config` file (create it)
- Handle missing `config.d/` directory (create it)
- Handle config.d file with no Host blocks
- Handle malformed lines gracefully (skip, don't crash)
- Verify file permissions are set to 0o600 on created files
- Verify directory permissions are set to 0o700
- **Target: 100% line + branch coverage**

### `test_manager.py`
- `list_hosts()` returns all hosts from all config.d files
- `list_hosts(filter="web")` returns matching hosts only
- `list_hosts(filter="nonexistent")` returns empty list
- `get_host("web-server")` returns correct entry
- `get_host("nonexistent")` returns None
- `add_host()` adds to correct config file
- `add_host()` with duplicate name raises error
- `add_host()` to nonexistent config file creates it
- `edit_host()` updates fields correctly
- `edit_host()` on nonexistent host raises error
- `remove_host()` removes from correct file
- `remove_host()` on nonexistent host raises error
- `connect_command()` returns valid SSH command
- `connect_command()` with custom port, identity file, etc.
- `connect_command()` on nonexistent host raises error
- `sftp_command()` returns valid SFTP command
- `list_config_files()` returns correct list
- `list_config_files()` with empty config.d returns empty list
- `create_config_file()` creates with correct permissions
- `create_config_file()` with existing name raises error
- `delete_config_file()` removes the file
- `delete_config_file()` on nonexistent file raises error
- **Target: 100% line + branch coverage**

---

## CLI Tests

Using Click's `CliRunner`:

```python
from click.testing import CliRunner
from cli.sshaman_cli import cli

def test_list_hosts(manager, ssh_dir):
    runner = CliRunner()
    result = runner.invoke(cli, ['list', '--ssh-dir', str(ssh_dir)])
    assert result.exit_code == 0
    assert 'web-server' in result.output
    assert 'db-server' in result.output

def test_add_host(manager, ssh_dir):
    runner = CliRunner()
    result = runner.invoke(cli, [
        'add', 'new-host',
        '--hostname', '10.0.0.1',
        '--user', 'root',
        '--ssh-dir', str(ssh_dir)
    ])
    assert result.exit_code == 0
    # Verify it was actually written
    ...

def test_remove_host_with_confirm(manager, ssh_dir):
    runner = CliRunner()
    result = runner.invoke(cli, ['remove', 'web-server', '--ssh-dir', str(ssh_dir)], input='y\n')
    assert result.exit_code == 0
    ...
```

---

## TUI Tests

Using Textual's `pilot`:

```python
from textual.pilot import Pilot
from tui.app import SSHaManApp

async def test_host_list_displays(manager):
    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        # Check that hosts are displayed
        table = app.query_one("#host-table")
        assert table.row_count == 2

async def test_add_host_screen(manager):
    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        await pilot.press("a")  # Open add screen
        # Verify add screen is displayed
        ...

async def test_connect_exits_with_command(manager):
    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        await pilot.press("enter")  # Select first host
        await pilot.press("c")     # Connect
        # Verify app exited with connect command
        ...
```

---

## Coverage Targets

**Goal: as close to 100% as possible across the entire project.**

| Module | Target | Notes |
|--------|--------|-------|
| `backend/host_entry.py` | 100% | Pure data model + serialization — fully testable |
| `backend/ssh_config.py` | 100% | File I/O with `tmp_path` — fully testable |
| `backend/manager.py` | 100% | Orchestration logic — fully testable |
| `backend/migrate.py` | 100% | Migration logic — fully testable with fixtures |
| `cli/sshaman_cli.py` | 98%+ | All commands via `CliRunner`; `pragma: no cover` only on `os.execvp` calls |
| `tui/app.py` | 95%+ | Textual `pilot` tests; `pragma: no cover` on process-replacing connect actions |
| `tui/screens/*.py` | 95%+ | Screen compose/mount/actions testable via `pilot` |
| `entrypoint.py` | 95%+ | `pragma: no cover` on `if __name__ == "__main__"` guard only |

### pytest-cov Configuration

Add to `pyproject.toml` (or `setup.cfg`):
```toml
[tool.pytest.ini_options]
addopts = "--cov=sshaman --cov-report=term-missing --cov-fail-under=95"

[tool.coverage.run]
branch = true
source = ["sshaman"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
]
show_missing = true
fail_under = 95
```

### `# pragma: no cover` Policy

Use sparingly and **always with a justifying comment**. Valid uses:

```python
# Process-replacing calls (cannot return in tests)
os.execvp("ssh", args)  # pragma: no cover — replaces process

# Entry point guards
if __name__ == "__main__":  # pragma: no cover
    cli()

# Defensive unreachable branches
else:  # pragma: no cover — exhaustive match above
    raise AssertionError(f"Unexpected action: {action}")
```

Invalid uses (write tests instead):
- Error handling paths — test with bad input
- Rare but reachable branches — create fixtures that trigger them
- "Too hard to test" logic — refactor to make it testable

---

## Files to Delete

- `tests/setup_tests.py` — replaced by `conftest.py`
- `tests/util_tests.py` — `print_diff` is unused/broken
- `tests/dev_test_sshaman.py` — manual dev script, not a test
- `tests/test_sshman.py` — replaced by `test_backend/`
- `tests/test_cli.py` — rewritten

---

## Tasks

- [ ] Create `tests/conftest.py` with `tmp_path` fixtures
- [ ] Write `test_backend/test_host_entry.py`
- [ ] Write `test_backend/test_ssh_config.py`
- [ ] Write `test_backend/test_manager.py`
- [ ] Rewrite `tests/test_cli.py`
- [ ] Write `tests/test_tui.py`
- [ ] Remove old test files
- [ ] Set up `pytest-cov` configuration in `pyproject.toml` with `--cov-fail-under=95`
- [ ] Add `# pragma: no cover` with comments on `os.execvp` calls and `__main__` guards
- [ ] Verify 95%+ coverage across all modules before merging
- [ ] Add GitHub Actions CI workflow (`.github/workflows/test.yml`) with coverage gate
- [ ] Add coverage badge to README
