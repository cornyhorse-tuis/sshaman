# Phase 7: Path to 100% Test Coverage

> **Status**: Not started
> **Current coverage**: 96.37% (290 tests, all passing)
> **Target**: 100% with preference order: unit tests → mocks → `# pragma: no cover`

---

## Philosophy

Coverage should be achieved through **this strict hierarchy**:

1. **Unit tests** — exercise the actual code path end-to-end using real (tmp-dir) fixtures.
2. **Mocks** — only when the code path is genuinely hard to trigger (e.g. filesystem failures, OS-level errors). Keep mocks surgical: mock one thing, assert the behaviour.
3. **`# pragma: no cover`** — absolute last resort, only for code that **replaces the process** (`os.execvp`) or is an `__main__` guard. Every use must have an inline comment explaining *why*.

---

## Gap Inventory

### Gap 1: `backend/ssh_config.py` — `_safe_write` exception cleanup (lines 281-283)

```python
except Exception:
    tmp.unlink(missing_ok=True)
    raise
```

**What it does**: When the atomic write (tempfile → `replace()`) fails, the temp file is cleaned up before re-raising.

**How to test** (mock):
- Mock `Path.replace` to raise `OSError`.
- Call a method that triggers `_safe_write` (e.g. `write_host()`).
- Assert the exception propagates **and** the temp file does not remain on disk.

```python
def test_safe_write_cleans_up_on_failure(config_manager, tmp_path, monkeypatch):
    """_safe_write removes the temp file when the rename step fails."""
    from backend.host_entry import HostEntry

    entry = HostEntry(name="boom", hostname="1.2.3.4")

    original_replace = Path.replace

    def failing_replace(self, target):
        raise OSError("disk on fire")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="disk on fire"):
        config_manager.write_host(entry, "test-file")

    # No stale .tmp files should remain
    tmp_files = list(config_manager.config_d.glob("*.tmp"))
    assert tmp_files == []
```

**Priority**: Medium — defensive code, but good to prove it works.

---

### Gap 2: `backend/ssh_config.py` — `_set_permissions` no-op branch (lines 360-361)

```python
def _set_permissions(path: Path, mode: int) -> None:
```

**What it does**: Skips `chmod` if the file already has the correct permissions.

**How to test** (unit test):
- Create a file, manually set it to `0o600`.
- Call `_set_permissions(path, 0o600)`.
- Confirm `os.chmod` was **not** called (use `monkeypatch` on `os.chmod` to track calls).

```python
def test_set_permissions_noop_when_already_correct(tmp_path, monkeypatch):
    """_set_permissions skips chmod when mode already matches."""
    f = tmp_path / "already-correct"
    f.write_text("x")
    f.chmod(0o600)

    calls = []
    original_chmod = os.chmod
    monkeypatch.setattr(os, "chmod", lambda p, m: calls.append((p, m)))

    from backend.ssh_config import _set_permissions, _FILE_MODE
    _set_permissions(f, _FILE_MODE)
    assert calls == []  # no chmod needed
```

**Priority**: Low — the logic is trivial, but it's an easy win.

---

### Gap 3: `backend/migrate.py` — force-overwrite write path (lines 112-113)

**What it does**: When `force=True` and the target config.d file already exists, the migration proceeds and overwrites it.

**How to test** (unit test — no mocks needed):
1. Run a first migration to create the target file.
2. Run a second migration with `force=True` on the same target.
3. Assert no error is raised, the file is overwritten, and the result contains the expected entries.

```python
def test_migrate_force_overwrites_existing_target(legacy_config_dir, config_manager):
    """force=True allows overwriting an existing target file."""
    from backend.migrate import migrate

    # First migration creates the file
    migrate(source=legacy_config_dir, config_manager=config_manager,
            config_file="target", force=False)

    # Second migration with force=True should succeed
    result = migrate(source=legacy_config_dir, config_manager=config_manager,
                     config_file="target", force=True)

    assert len(result.migrated) > 0
    assert not result.errors
```

**Priority**: Medium — exercises a real user scenario (re-migration).

---

### Gap 4: `tui/screens/config_files.py` — `NewConfigFileScreen` regex rejection (lines 168-172)

```python
if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
    self.notify(
        "Name may only contain letters, digits, hyphens, underscores, and dots.",
        severity="error",
    )
    return
```

**What it does**: Rejects config file names with invalid characters (spaces, slashes, etc.).

**How to test** (Textual pilot):
- Mount `NewConfigFileScreen`.
- Type an invalid name (e.g. `"bad name!"`) into the input.
- Click the Create button.
- Assert the screen was **not** dismissed (i.e. the notification fired and input stayed open).

```python
async def test_new_config_file_rejects_invalid_name(manager):
    """NewConfigFileScreen rejects names with invalid characters."""
    from tui.screens.config_files import NewConfigFileScreen

    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        screen = NewConfigFileScreen()
        app.push_screen(screen)
        await pilot.pause()

        inp = screen.query_one("#input-name", Input)
        inp.value = "bad name!"
        await pilot.click("#btn-create")
        await pilot.pause()

        # Screen should still be mounted (not dismissed)
        assert screen.is_attached
```

**Priority**: Medium — user-facing validation path.

---

### Gap 5: `tui/screens/host_form.py` — HostEntry validation error (lines 174-176)

```python
except Exception as exc:
    self.notify(f"Validation error: {exc}", severity="error")
    return
```

**What it does**: Catches Pydantic validation errors when form inputs produce an invalid `HostEntry`.

**How to test** (Textual pilot + mock):
- Mount `HostFormScreen`.
- Monkeypatch `HostEntry.__init__` to raise `ValueError("bad hostname")`.
- Fill in form fields and trigger save.
- Assert the screen stays open and a notification was shown.

Alternatively, trigger it organically by finding an input combination that fails Pydantic validation (e.g. empty hostname after clearing the field — though the form may guard against that separately). The mock approach is more reliable.

```python
async def test_host_form_shows_validation_error(manager, monkeypatch):
    """HostFormScreen shows notification on HostEntry validation failure."""
    from tui.screens.host_form import HostFormScreen

    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        screen = HostFormScreen(config_files=["default"])
        app.push_screen(screen)
        await pilot.pause()

        # Fill in valid-looking data
        screen.query_one("#input-name", Input).value = "test"
        screen.query_one("#input-hostname", Input).value = "example.com"

        # Make HostEntry raise during construction
        from backend.host_entry import HostEntry
        original_init = HostEntry.__init__
        def broken_init(self, **kwargs):
            raise ValueError("synthetic validation error")
        monkeypatch.setattr(HostEntry, "__init__", broken_init)

        await pilot.click("#btn-save")
        await pilot.pause()

        assert screen.is_attached  # form stayed open
```

**Priority**: Medium — ensures error handling doesn't crash the TUI.

---

### Gap 6: `tui/app.py` — `_get_selected_host_name` exception fallback (lines 110-111)

```python
except Exception:
    return None
```

**What it does**: Returns `None` if `coordinate_to_cell_key` raises unexpectedly (e.g. table in inconsistent state).

**How to test** (mock):
- Monkeypatch `DataTable.coordinate_to_cell_key` to raise `IndexError`.
- Call `_get_selected_host_name()`.
- Assert it returns `None` instead of crashing.

```python
async def test_get_selected_host_name_returns_none_on_exception(manager, monkeypatch):
    app = SSHaManApp(manager=manager)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#host-table", DataTable)
        monkeypatch.setattr(table, "coordinate_to_cell_key",
                            lambda coord: (_ for _ in ()).throw(IndexError("bad")))
        assert app._get_selected_host_name() is None
```

**Priority**: Low — defensive code, but trivial to test.

---

### Gap 7: `tui/app.py` — `_on_add_host_result` config_file attribute (line 170)

```python
config_file = getattr(entry, "_config_file", "sshaman-hosts")
```

**What it does**: Falls back to `"sshaman-hosts"` when the entry doesn't have a `_config_file` attribute.

**How to test** (unit test):
- Call `_on_add_host_result` with a plain `HostEntry` (no `_config_file` attr).
- Assert the host is added to the default `"sshaman-hosts"` file.

This is partially tested already via the add-host TUI flow. A targeted test would call the callback directly.

**Priority**: Low.

---

### Gap 8: `tui/app.py` — `_on_edit_host_result` identity_file branch (line 207)

**What it does**: Passes `identity_file` through to `manager.edit_host()`.

**How to test** (Textual pilot):
- Add a host, then open the edit form.
- Set an `identity_file` value in the form.
- Save and verify the host was updated with the identity file.

**Priority**: Low — straightforward extension of existing edit tests.

---

### Gap 9: `tui/app.py` — `action_manage_files` (line 249)

```python
def action_manage_files(self) -> None:
    self.push_screen(ConfigFilesScreen(), callback=self._on_files_closed)
```

**How to test** (Textual pilot):
- Trigger the `manage_files` action (press the keybinding).
- Assert `ConfigFilesScreen` is pushed.
- Dismiss it and verify hosts are refreshed.

**Priority**: Medium — exercises a real TUI workflow.

---

### Gap 10: `cli/sshaman_cli.py` — TUI launch path (lines 46-58)

```python
if ctx.invoked_subcommand is None:
    from tui.app import SSHaManApp
    app = SSHaManApp(manager=ctx.obj["manager"])
    result = app.run()
    if result:
        action, host_name = result
        ...
```

**How to test** (mock):
- Mock `SSHaManApp.run` to return `None` (user quit without action).
- Invoke `cli` via `CliRunner` with no subcommand.
- Assert exit code 0 and that the TUI was instantiated.
- Second test: mock `SSHaManApp.run` to return `("ssh", "myhost")` and mock `os.execvp` to capture the call (since `execvp` replaces the process, the mock prevents that).

```python
def test_cli_no_subcommand_launches_tui(manager, monkeypatch):
    """Invoking `sshaman` with no subcommand launches the TUI."""
    from unittest.mock import MagicMock
    mock_app = MagicMock()
    mock_app.run.return_value = None

    monkeypatch.setattr("cli.sshaman_cli.SSHaManApp", lambda **kw: mock_app)

    runner = CliRunner()
    result = runner.invoke(cli, [], obj={"manager": manager})
    assert result.exit_code == 0
    mock_app.run.assert_called_once()


def test_cli_no_subcommand_tui_ssh_action(manager, monkeypatch):
    """TUI returning an ssh action triggers os.execvp."""
    from unittest.mock import MagicMock
    mock_app = MagicMock()
    mock_app.run.return_value = ("ssh", "myhost")

    monkeypatch.setattr("cli.sshaman_cli.SSHaManApp", lambda **kw: mock_app)

    execvp_calls = []
    monkeypatch.setattr(os, "execvp", lambda cmd, args: execvp_calls.append((cmd, args)))

    runner = CliRunner()
    result = runner.invoke(cli, [], obj={"manager": manager})
    assert len(execvp_calls) == 1
```

**Priority**: High — this is the largest uncovered block (~13 lines) and a primary user flow.

---

### Gap 11: `cli/sshaman_cli.py` — `show` command rendering branches (lines 112, 366, 421, 439)

**What it does**: Various Rich formatting branches in `show` and `config show` / `migrate` output.

**How to test** (unit test):
- Create hosts with `local_forwards`, `extra_options`, `proxy_jump`, `forward_agent` set.
- Run `show` and assert the output contains the expected formatted strings.
- For `migrate`: run with `--dry-run` and verify the "Would write" / "Run without --dry-run" output.

```python
def test_show_all_fields(manager):
    """show command renders all optional fields."""
    entry = HostEntry(name="full", hostname="1.2.3.4", user="admin",
                      port=2222, proxy_jump="bastion",
                      forward_agent=True, local_forwards=["8080:localhost:80"],
                      extra_options={"RequestTTY": "yes"})
    manager.add_host(entry, config_file="test")

    runner = CliRunner()
    result = runner.invoke(cli, ["show", "full"], obj={"manager": manager})
    assert "ProxyJump" in result.output
    assert "bastion" in result.output
    assert "ForwardAgent" in result.output
    assert "LocalForward" in result.output
    assert "Requesttty" in result.output  # capitalized by the loop
```

**Priority**: Medium.

---

## Integration Tests (New)

Beyond per-function coverage, add a small suite of end-to-end CLI integration tests:

### Integration 1: Full host lifecycle via CLI

```python
def test_host_lifecycle_cli(manager):
    """Add → list → show → edit → connect-cmd → remove via CLI."""
    runner = CliRunner()
    obj = {"manager": manager}

    # Add
    r = runner.invoke(cli, ["add", "web1", "--hostname", "10.0.0.1",
                            "--user", "deploy", "--port", "22"], obj=obj)
    assert r.exit_code == 0

    # List
    r = runner.invoke(cli, ["list"], obj=obj)
    assert "web1" in r.output

    # Show
    r = runner.invoke(cli, ["show", "web1"], obj=obj)
    assert "10.0.0.1" in r.output

    # Edit
    r = runner.invoke(cli, ["edit", "web1", "--hostname", "10.0.0.2"], obj=obj)
    assert r.exit_code == 0

    # Verify edit
    r = runner.invoke(cli, ["show", "web1"], obj=obj)
    assert "10.0.0.2" in r.output

    # Remove
    r = runner.invoke(cli, ["remove", "web1", "--yes"], obj=obj)
    assert r.exit_code == 0

    # Verify removed
    r = runner.invoke(cli, ["list"], obj=obj)
    assert "web1" not in r.output
```

### Integration 2: Config file management lifecycle

```python
def test_config_file_lifecycle_cli(manager):
    """init → config create → config list → config show → config delete."""
    runner = CliRunner()
    obj = {"manager": manager}

    r = runner.invoke(cli, ["config", "init"], obj=obj)
    assert r.exit_code == 0

    r = runner.invoke(cli, ["config", "create", "my-servers"], obj=obj)
    assert r.exit_code == 0

    r = runner.invoke(cli, ["config", "list"], obj=obj)
    assert "my-servers" in r.output

    r = runner.invoke(cli, ["config", "show", "my-servers"], obj=obj)
    assert r.exit_code == 0

    r = runner.invoke(cli, ["config", "delete", "my-servers", "--yes"], obj=obj)
    assert r.exit_code == 0
```

### Integration 3: Migration end-to-end

```python
def test_migrate_dry_run_then_live(legacy_config_dir, manager):
    """Dry-run shows preview, live run writes hosts, force re-runs."""
    runner = CliRunner()
    obj = {"manager": manager}

    # Dry run
    r = runner.invoke(cli, ["migrate", "--source", str(legacy_config_dir),
                            "--dry-run"], obj=obj)
    assert "dry run" in r.output.lower()
    assert "Would write" in r.output

    # Live run
    r = runner.invoke(cli, ["migrate", "--source", str(legacy_config_dir)], obj=obj)
    assert r.exit_code == 0

    # Force re-run
    r = runner.invoke(cli, ["migrate", "--source", str(legacy_config_dir),
                            "--force"], obj=obj)
    assert r.exit_code == 0
```

**Priority**: High — integration tests catch wiring bugs that unit tests miss.

---

## `# pragma: no cover` — Acceptable Uses

These lines should remain excluded and do **not** need test coverage:

| Location | Reason |
|---|---|
| `cli/sshaman_cli.py` — `os.execvp(cmd[0], cmd)` (×2) | Replaces the process; cannot return in tests |
| `entrypoint.py` — `if __name__ == "__main__":` | Entry point guard, excluded in `pyproject.toml` |
| `cli/sshaman_cli.py` — `if __name__ == "__main__":` | Entry point guard |

**No new `# pragma: no cover` should be added.** All remaining gaps are testable via unit tests or mocks.

---

## Execution Order

| Step | Gaps | Est. Tests | Approach | Priority |
|---|---|---|---|---|
| 1 | Gap 10 (CLI TUI launch) | 3 | Mock `SSHaManApp.run` + `os.execvp` | High |
| 2 | Gap 11 (CLI output branches) | 3 | Unit tests with rich-output hosts | Medium |
| 3 | Integration tests 1-3 | 3 | CliRunner end-to-end | High |
| 4 | Gap 3 (migrate force-overwrite) | 1 | Unit test, no mocks | Medium |
| 5 | Gap 1 (_safe_write cleanup) | 1 | Mock `Path.replace` | Medium |
| 6 | Gap 4 (NewConfigFile regex) | 1 | Textual pilot | Medium |
| 7 | Gap 5 (HostForm validation) | 1 | Textual pilot + mock | Medium |
| 8 | Gap 9 (manage_files action) | 1 | Textual pilot | Medium |
| 9 | Gap 6 (get_selected exception) | 1 | Mock DataTable method | Low |
| 10 | Gap 2 (_set_permissions noop) | 1 | Monkeypatch os.chmod | Low |
| 11 | Gap 7 (config_file fallback) | 1 | Direct callback call | Low |
| 12 | Gap 8 (edit identity_file) | 1 | Textual pilot | Low |

**Total: ~18 new tests to reach 100% meaningful coverage.**

---

## Verification

After implementing all tests:

```bash
# Full run with coverage
./scripts/test

# Confirm 100%
python -m pytest tests/ --cov=backend --cov=cli --cov=tui \
    --cov-report=term-missing --cov-branch --cov-fail-under=100
```

Update `pyproject.toml` once stable:

```toml
"--cov-fail-under=100"
```
