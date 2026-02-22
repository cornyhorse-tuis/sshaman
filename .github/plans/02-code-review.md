# Code Review — Bugs, Technical Debt, and Inconsistencies

> **Created**: 2026-02-22  
> **Scope**: Full review of all current source files

---

## Critical Issues

### 1. CLI has two conflicting `cli()` definitions (`cli/sshaman_cli.py`)
**Lines 9-14 and 17-19** define `cli` twice — first as an `invoke_without_command` group that falls through to the TUI, then immediately overwritten by a plain `@click.group()`. The first definition is dead code and the TUI-launch-on-no-args behavior is broken from the CLI side (it only works via `entrypoint.py`'s manual `sys.argv` check).

### 2. Passwords stored in config files (`entities/server.py`)
The `Server` model has a `password` field that gets serialized to JSON and saved to disk in plaintext. This is a security risk. SSH tools should rely on key-based auth or ssh-agent, never stored passwords. The test fixtures also use `password='12345'`.

### 3. Global mutable state for config path (`configs/path.py`)
`CONFIG_PATH` is a module-level global, mutated via `set_config_path()`. This causes:
- Test pollution (one test changes the path, affects another)
- Thread-safety issues
- Hard to reason about which path is being used at any point
- The `SSHAMan.__init__` both reads and writes the global, creating circular confusion

### 4. `ServerGroup.__init__` creates directories as a side effect
Instantiating a `ServerGroup` immediately creates a directory on the filesystem. This makes it impossible to use the model for read-only operations, testing, or validation without filesystem side effects.

### 5. TUI duplicates backend config-reading logic (`tui/ssh_connections/ssh_connect.py`)
The `retrieve_file()` function reads JSON config files and builds SSH commands independently from the backend. If the config format changes, this code won't be updated. The TUI should call the backend's `connect_command()` instead.

---

## Bugs

### 6. `Server.__str__` returns `None` (`entities/server.py`)
```python
def __str__(self):
    print(f'  {self.alias} - {self.host}:{self.port}')
```
This **prints** instead of **returning** a string. `str(server)` returns `None`.

### 7. `action_connect_ssh` silently fails on non-JSON selection (`tui/tree.py`)
```python
if '.json' not in str(path).lower():
    pass  # ← silently does nothing
```
Should display a user-facing message like "Select a server, not a group."

### 8. `action_connect_sftp` uses `path.lower()` on a Path object (`tui/tree.py`)
```python
if '.json' not in path.lower():  # ← Path has no .lower() method
```
This will raise `AttributeError`. The SSH action correctly uses `str(path).lower()` but the SFTP action doesn't.

### 9. `list-all` CLI command ignores `--config_path` (`cli/sshaman_cli.py`)
```python
def list_all(config_path):
    manager = SSHAMan()  # ← config_path argument is ignored
```
The `config_path` option is accepted but never passed to `SSHAMan()`.

### 10. `util_tests.print_diff` called with wrong types (`tests/test_sshman.py:62`)
```python
print_diff(expected=expected, actual=actual)
```
At this point `expected` and `actual` are `list` objects (from `sorted()`), but `print_diff` calls `.splitlines()` on them, which is a string method. This will crash if the assertion fails.

### 11. Test fixtures write to real filesystem (`tests/setup_tests.py`)
The `sshaman_setup` fixture writes to `~/.config/test_sshaman/` — a real path in the user's home directory. Should use `tmp_path` instead to avoid polluting the filesystem and to enable parallel test execution.

### 12. `generate_default_config` creates group `sg1` but tests expect `subgroup1` (`tests/setup_tests.py`)
```python
g1.make_child('sg1', parent_absolute_path=g1.absolute_path)
```
But `test_load_config` asserts:
```python
correct_contents = ['subgroup1', 'vm1.json', 'vm2.json']
```
The group is named `sg1` but the test expects `subgroup1`. Then `sshaman_setup` also calls `smn.make_group('group1.subgroup1.subgroup2')` which creates the `subgroup1` directory, so the test may pass by accident, but the `sg1` directory is orphaned.

### 13. `vm2` is added to `sg1` but test expects it in `group1` (`tests/setup_tests.py`)
```python
sg2 = g1.children['sg1']
sg2.add_server(s2)  # ← adds vm2 to sg1/, not group1/
```
But `test_load_config` expects `vm2.json` in `group1/`:
```python
correct_contents = ['subgroup1', 'vm1.json', 'vm2.json']
```
This suggests tests may be passing for the wrong reasons or are currently broken.

---

## Technical Debt

### 14. Uses `os.path` everywhere instead of `pathlib.Path`
Every file uses `os.path.join`, `os.path.exists`, `os.makedirs`, etc. Modern Python should use `pathlib.Path` for cleaner, more readable code.

### 15. No type hints on most functions
Functions in `sshman.py`, `ssh_connect.py`, and test files lack type annotations.

### 16. Commented-out code throughout
- `tui/tree.py`: Many bindings commented out (edit, delete, refresh, add-server, make-group, help, new-file)
- `tui/ssh_connections/ssh_connect.py`: Forward port handling commented out
- `cli/sshaman_cli.py`: `test_make_group` and `test_add_server` commented out
- These represent planned but unimplemented features

### 17. Empty placeholder files
- `tui/textual_extensions/custom_directory_tree.py` — empty
- `tui/ui/__init__.py` — empty package with no modules

### 18. `entrypoint.py` uses raw `sys.argv` instead of Click's built-in dispatch
Click's `invoke_without_command=True` is the proper way to handle "no subcommand → launch TUI". The manual `len(sys.argv) == 1` check duplicates this.

### 19. `Server.serialize()` is redundant
```python
def serialize(self):
    return json.loads(self.model_dump_json(indent=4))
```
This serializes to JSON string then immediately parses back to dict. Should just use `self.model_dump()`.

### 20. `NotImplementedError` raised after `raise` in `add_server` (`management/sshman.py`)
```python
if kwargs.get('start_commands'):
    raise NotImplementedError("Start commands are not supported yet.")
    kwargs['start_commands'] = list(kwargs['start_commands'])  # ← unreachable
```

### 21. No error handling or user feedback in CLI commands
CLI commands don't catch exceptions or provide useful error messages. A missing group, invalid port, or filesystem error will produce raw Python tracebacks.

### 22. `add_server` doesn't prevent duplicate aliases
Nothing stops a user from adding two servers with the same alias in the same group, creating conflicting JSON files.

### 23. `connect_shell`/`connect_sftp` build commands via string concatenation
```python
command = f"ssh {idf} {config['user']}@{config['host']} -p {config['port']}"
```
This is fragile and potentially unsafe with special characters in hostnames or usernames. After migration, we should use `ssh <host-alias>` since the config will be in `~/.ssh/config` and SSH knows how to resolve it.

### 24. TUI `CodeBrowser` name is misleading
The main TUI class is called `CodeBrowser` (copied from a Textual example). Should be renamed to something like `SSHaManApp`.

### 25. The TUI exits to run SSH commands
The app sets `self.command`, calls `self.exit()`, and then `main()` runs `subprocess.run()` after the TUI exits. This works but is clunky. Consider using `os.execvp()` to replace the process, or re-launching the TUI after disconnect.

---

## Summary of Actions Needed

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | Critical | Duplicate `cli()` | Remove first definition |
| 2 | Critical | Passwords in config | Remove password field entirely |
| 3 | Critical | Global mutable config path | Pass paths explicitly, delete `set_config_path` |
| 4 | High | Side-effect in `__init__` | Separate model from filesystem ops |
| 5 | High | TUI duplicates backend | TUI calls backend, not its own file reader |
| 6 | Medium | `__str__` returns None | Return the string |
| 7 | Medium | Silent failure in TUI | Show user message |
| 8 | Medium | `Path.lower()` crash | Use `str(path).lower()` |
| 9 | Medium | `config_path` ignored | Pass it through |
| 10 | Medium | Wrong types in `print_diff` | Fix test helper |
| 11 | Medium | Tests write to real fs | Use `tmp_path` |
| 12 | Medium | Test data mismatch | Fix fixture |
| 13 | Medium | Test data mismatch | Fix fixture |
| 14 | Low | `os.path` usage | Migrate to `pathlib` |
| 15 | Low | Missing type hints | Add throughout |
| 16 | Low | Commented-out code | Remove or implement |
| 17 | Low | Empty files | Remove or implement |
| 18 | Low | Raw sys.argv check | Use Click dispatch |
| 19 | Low | Redundant serialize | Use `model_dump()` |
| 20 | Low | Unreachable code | Remove dead code |
| 21 | Low | No error handling | Add proper error handling |
| 22 | Low | No duplicate check | Validate uniqueness |
| 23 | Low | String concat commands | Use host alias after migration |
| 24 | Low | Misleading class name | Rename to `SSHaManApp` |
| 25 | Low | Exit-to-connect pattern | Improve UX flow |

Most of these are resolved naturally by the revamp (new backend, new CLI, new TUI). The code review is provided here so the implementing agent understands what's wrong and doesn't carry forward any of these patterns.
