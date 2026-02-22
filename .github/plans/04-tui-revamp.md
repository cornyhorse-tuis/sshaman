# Phase 3: TUI Revamp

> **Status**: Not started  
> **Depends on**: Phase 1 (Backend)  
> **Can be done in parallel with**: Phase 2 (CLI)

---

## Overview

Rewrite the TUI from scratch using Textual, backed entirely by `backend/manager.py`. The TUI must not read config files, build SSH commands, or manage filesystem state on its own.

---

## Current TUI Problems

### Architecture
1. **Directly reads JSON config files** via `tui/ssh_connections/ssh_connect.py` — duplicates backend logic
2. **Uses Textual's `DirectoryTree` to browse `~/.config/sshaman/`** — this was a quick hack; after migration to `~/.ssh/config.d/`, browsing raw files makes no sense
3. **`file_operations/new_file.py`** calls `SSHAMan` directly instead of going through a shared backend
4. **Named `CodeBrowser`** — leftover from the Textual example it was based on

### Bugs
5. **`action_connect_sftp`** calls `path.lower()` on a `Path` object → `AttributeError`
6. **Silent failure** when selecting a directory instead of a JSON file for connect
7. **Exit-to-connect pattern** — the app exits, then `main()` runs `subprocess.run()`. If the SSH command fails, error handling is inconsistent

### Missing Features
8. No ability to **add hosts** from the TUI
9. No ability to **edit hosts** from the TUI
10. No ability to **remove hosts** from the TUI
11. No ability to **manage config.d files** from the TUI
12. No **search/filter** functionality
13. No **host detail view** — selecting a file shows raw JSON syntax-highlighted, not a friendly display
14. Most key bindings are **commented out** (edit, delete, add, refresh, etc.)

---

## New TUI Design

### Screens

```
┌─ SSHaManApp ─────────────────────────────────────────┐
│                                                       │
│  ┌─ HostListScreen (default) ──────────────────────┐ │
│  │  Filter: [______________]                       │ │
│  │                                                  │ │
│  │  Config: 10-work-servers                        │ │
│  │    ▸ web-prod     10.0.1.50    deploy    :22    │ │
│  │    ▸ db-prod      10.0.1.51    admin     :2222  │ │
│  │  Config: 20-home-lab                            │ │
│  │    ▸ nas          192.168.1.10 matt      :22    │ │
│  │    ▸ pi           192.168.1.20 pi        :22    │ │
│  │                                                  │ │
│  │  [a]dd  [e]dit  [d]elete  [c]onnect  [s]ftp    │ │
│  │  [/]search  [f]iles  [q]uit                     │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ HostDetailScreen (modal) ──────────────────────┐ │
│  │  Host: web-prod                                  │ │
│  │  HostName: 10.0.1.50                            │ │
│  │  User: deploy                                    │ │
│  │  Port: 22                                        │ │
│  │  IdentityFile: ~/.ssh/work_key                  │ │
│  │  Source: ~/.ssh/config.d/10-work-servers         │ │
│  │                                                  │ │
│  │  [Enter] Connect  [e] Edit  [Esc] Back          │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ AddHostScreen (modal) ─────────────────────────┐ │
│  │  Host alias:    [______________]                 │ │
│  │  HostName:      [______________]                 │ │
│  │  User:          [______________]                 │ │
│  │  Port:          [22____________]                 │ │
│  │  IdentityFile:  [______________]                 │ │
│  │  Config file:   [▾ sshaman-hosts ]              │ │
│  │                                                  │ │
│  │  [Enter] Save  [Esc] Cancel                     │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ EditHostScreen (modal) ────────────────────────┐ │
│  │  (same as AddHostScreen, pre-filled)            │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ ConfigFilesScreen (modal) ─────────────────────┐ │
│  │  Config Files in ~/.ssh/config.d/:              │ │
│  │    ▸ 10-work-servers  (3 hosts)                 │ │
│  │    ▸ 20-home-lab      (2 hosts)                 │ │
│  │    ▸ sshaman-hosts    (0 hosts)                 │ │
│  │                                                  │ │
│  │  [n]ew  [d]elete  [Esc] Back                    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ ConfirmScreen (modal) ─────────────────────────┐ │
│  │  Are you sure you want to delete "web-prod"?    │ │
│  │  [y] Yes  [n] No                                │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

### Key Bindings

| Key | Action | Screen |
|-----|--------|--------|
| `a` | Add new host | HostList |
| `e` | Edit selected host | HostList, HostDetail |
| `d` | Delete selected host (with confirm) | HostList |
| `c` | Connect via SSH | HostList, HostDetail |
| `s` | Connect via SFTP | HostList, HostDetail |
| `/` | Search/filter hosts | HostList |
| `Enter` | View host detail | HostList |
| `f` | Manage config files | HostList |
| `q` | Quit | All |
| `Esc` | Go back / close modal | Modal screens |

---

## File Structure

```
tui/
├── __init__.py
├── app.py                  # SSHaManApp (Textual App subclass)
├── app.tcss                # Global stylesheet
├── screens/
│   ├── __init__.py
│   ├── host_list.py        # HostListScreen — main screen
│   ├── host_detail.py      # HostDetailScreen — show host info
│   ├── host_form.py        # AddHostScreen / EditHostScreen (reusable form)
│   ├── config_files.py     # ConfigFilesScreen — manage config.d files
│   └── confirm.py          # ConfirmScreen — yes/no dialog
└── widgets/
    ├── __init__.py
    ├── host_table.py       # DataTable or ListView of hosts
    └── filter_input.py     # Search/filter input widget
```

---

## Implementation Notes

### The app must receive the backend manager

```python
class SSHaManApp(App):
    def __init__(self, manager: SSHManager, **kwargs):
        super().__init__(**kwargs)
        self.manager = manager
```

Both CLI and TUI instantiate `SSHManager` and pass it to the TUI app. The TUI never creates its own manager or reads config files.

### Host list should use Textual's `DataTable`

```python
from textual.widgets import DataTable

class HostListScreen(Screen):
    def compose(self):
        yield Header()
        yield Input(placeholder="Filter hosts...", id="filter")
        yield DataTable(id="host-table")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#host-table", DataTable)
        table.add_columns("Host", "HostName", "User", "Port", "Config File")
        self.refresh_hosts()

    def refresh_hosts(self, filter_text: str = ""):
        hosts = self.app.manager.list_hosts(filter=filter_text or None)
        table = self.query_one("#host-table", DataTable)
        table.clear()
        for host in hosts:
            table.add_row(
                host.name, host.hostname, host.user or "", 
                str(host.port), host.source_file.name if host.source_file else "",
                key=host.name
            )
```

### Connect action should exit the TUI and exec SSH

```python
def action_connect(self):
    host = self._get_selected_host()
    if host:
        self.app.exit(result=("ssh", host.name))

# In app.py:
def main(manager):
    app = SSHaManApp(manager=manager)
    result = app.run()
    if result:
        action, host_name = result
        if action == "ssh":
            cmd = manager.connect_command(host_name)
            os.execvp("ssh", cmd.split())
        elif action == "sftp":
            cmd = manager.sftp_command(host_name)
            os.execvp("sftp", cmd.split())
```

### Form screens should use Textual's Input widgets

```python
class HostFormScreen(ModalScreen):
    """Reusable form for adding/editing hosts."""

    def __init__(self, host: HostEntry | None = None, config_files: list[str] = None):
        super().__init__()
        self.host = host  # None for add, populated for edit
        self.config_files = config_files or []
```

---

## Modules to Delete

- `tui/tree.py` → replaced by `tui/app.py`
- `tui/tree.tcss` → replaced by `tui/app.tcss`
- `tui/ssh_connections/` → SSH command building moves to backend
- `tui/file_operations/` → host management moves to backend
- `tui/textual_extensions/custom_directory_tree.py` → empty, unused
- `tui/ui/` → empty, unused

---

## Tasks

- [ ] Create `tui/app.py` with `SSHaManApp` class
- [ ] Create `tui/screens/host_list.py` — main host list with DataTable
- [ ] Create `tui/screens/host_detail.py` — host detail view
- [ ] Create `tui/screens/host_form.py` — add/edit host form
- [ ] Create `tui/screens/config_files.py` — config file management
- [ ] Create `tui/screens/confirm.py` — confirmation dialog
- [ ] Create `tui/widgets/host_table.py` if needed
- [ ] Create `tui/app.tcss` stylesheet
- [ ] Implement all key bindings
- [ ] Implement SSH/SFTP connect via exit-and-exec pattern
- [ ] Delete old TUI modules
- [ ] Write TUI tests using Textual's `pilot` — target 95%+ coverage
- [ ] Test each screen: compose, mount, key bindings, data display
- [ ] Test form validation (empty fields, invalid port, duplicate host name)
- [ ] Test navigation flow: list → detail → edit → back
- [ ] Test filter/search updates the host table correctly
- [ ] Test confirm dialog returns correct result for yes/no
- [ ] Mark process-replacing connect actions with `# pragma: no cover`
