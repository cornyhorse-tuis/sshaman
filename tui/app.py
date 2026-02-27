"""SSHaMan TUI — Textual application.

This is the main TUI entry point.  It delegates all SSH config
operations to :class:`~backend.manager.SSHManager` and never reads
config files directly.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Input

from backend.host_entry import HostEntry
from backend.manager import DuplicateHostError, HostNotFoundError, SSHManager
from tui.screens.config_files import ConfigFilesScreen
from tui.screens.confirm import ConfirmScreen
from tui.screens.host_detail import HostDetailScreen
from tui.screens.host_form import HostFormScreen


class SSHaManApp(App[tuple[str, str] | None]):
    """SSH connection manager TUI.

    The app returns a ``(action, host_name)`` tuple when the user chooses
    to connect (``action`` is ``"ssh"`` or ``"sftp"``), or ``None`` if the
    user quits normally.

    Args:
        manager: The backend :class:`SSHManager` instance.
    """

    TITLE = "SSHaMan"
    CSS = """
    Screen {
        background: $surface-darken-1;
    }

    #filter-input {
        dock: top;
        width: 100%;
        margin-bottom: 1;
    }

    #host-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("a", "add_host", "Add", show=True),
        Binding("d", "delete_host", "Delete", show=True),
        Binding("e", "edit_host", "Edit", show=True),
        Binding("c", "connect_ssh", "SSH", show=True),
        Binding("s", "connect_sftp", "SFTP", show=True),
        Binding("f", "manage_files", "Files", show=True),
        Binding("slash", "focus_filter", "Search", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, manager: SSHManager, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.manager = manager

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Build the main UI."""
        yield Header()
        yield Input(placeholder="Filter hosts…", id="filter-input")
        yield DataTable(id="host-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the host table on startup."""
        table = self.query_one("#host-table", DataTable)
        table.add_columns("Host", "HostName", "User", "Port", "Config File")
        self._refresh_hosts()

    # ------------------------------------------------------------------
    # Host table helpers
    # ------------------------------------------------------------------

    def _refresh_hosts(self, filter_text: str = "") -> None:
        """Reload hosts from backend and repopulate the table."""
        table = self.query_one("#host-table", DataTable)
        table.clear()

        hosts = self.manager.list_hosts(filter=filter_text or None)
        for host in hosts:
            table.add_row(
                host.name,
                host.hostname,
                host.user or "",
                str(host.port),
                host.source_file.name if host.source_file else "",
                key=host.name,
            )

    def _get_selected_host_name(self) -> str | None:
        """Return the alias of the currently highlighted row, or None."""
        table = self.query_one("#host-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            return str(row_key.value)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Input / filter
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live-filter the host table as the user types."""
        if event.input.id == "filter-input":
            self._refresh_hosts(event.value)

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter-input", Input).focus()

    # ------------------------------------------------------------------
    # Row selection
    # ------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter key on a row → show host detail."""
        host_name = str(event.row_key.value)
        host = self.manager.get_host(host_name)
        if host is None:
            return
        self.push_screen(HostDetailScreen(host), callback=self._on_detail_result)

    def _on_detail_result(self, action: str | None) -> None:
        """Handle the result from the detail screen."""
        if action is None:
            return
        host_name = self._get_selected_host_name()
        if host_name:
            self.exit(result=(action, host_name))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_add_host(self) -> None:
        """Open the add-host form."""
        config_files = [f.name for f in self.manager.list_config_files()]
        if not config_files:
            config_files = ["sshaman-hosts"]
        self.push_screen(
            HostFormScreen(config_files=config_files),
            callback=self._on_add_host_result,
        )

    def _on_add_host_result(self, entry: HostEntry | None) -> None:
        """Handle save from the add-host form."""
        if entry is None:
            return
        config_file = getattr(entry, "_config_file", "sshaman-hosts")
        try:
            self.manager.add_host(entry, config_file=config_file)
            self.notify(f"Added {entry.name}")
            self._refresh_hosts()
        except DuplicateHostError as exc:
            self.notify(str(exc), severity="error")

    def action_edit_host(self) -> None:
        """Open the edit form for the selected host."""
        host_name = self._get_selected_host_name()
        if host_name is None:
            self.notify("No host selected.", severity="warning")
            return
        host = self.manager.get_host(host_name)
        if host is None:
            return
        config_files = [f.name for f in self.manager.list_config_files()]
        self.push_screen(
            HostFormScreen(host=host, config_files=config_files),
            callback=self._on_edit_host_result,
        )

    def _on_edit_host_result(self, entry: HostEntry | None) -> None:
        """Handle save from the edit form."""
        if entry is None:
            return
        try:
            self.manager.edit_host(
                entry.name,
                hostname=entry.hostname,
                user=entry.user,
                port=entry.port,
                identity_file=entry.identity_file,
            )
            self.notify(f"Updated {entry.name}")
            self._refresh_hosts()
        except HostNotFoundError as exc:
            self.notify(str(exc), severity="error")

    def action_delete_host(self) -> None:
        """Delete the selected host after confirmation."""
        host_name = self._get_selected_host_name()
        if host_name is None:
            self.notify("No host selected.", severity="warning")
            return
        self.push_screen(
            ConfirmScreen(f"Delete host '{host_name}'?"),
            callback=self._on_delete_confirmed,
        )

    def _on_delete_confirmed(self, confirmed: bool) -> None:
        """Process deletion after confirmation."""
        if not confirmed:
            return
        host_name = self._get_selected_host_name()
        if host_name is None:
            return
        try:
            self.manager.remove_host(host_name)
            self.notify(f"Deleted {host_name}")
            self._refresh_hosts()
        except HostNotFoundError as exc:
            self.notify(str(exc), severity="error")

    def action_connect_ssh(self) -> None:
        """Exit the TUI and connect via SSH."""
        host_name = self._get_selected_host_name()
        if host_name is None:
            self.notify("No host selected.", severity="warning")
            return
        self.exit(result=("ssh", host_name))

    def action_connect_sftp(self) -> None:
        """Exit the TUI and connect via SFTP."""
        host_name = self._get_selected_host_name()
        if host_name is None:
            self.notify("No host selected.", severity="warning")
            return
        self.exit(result=("sftp", host_name))

    def action_manage_files(self) -> None:
        """Open the config file management screen."""
        self.push_screen(ConfigFilesScreen(), callback=self._on_files_closed)

    def _on_files_closed(self, _result: None) -> None:
        """Refresh after returning from config files screen."""
        self._refresh_hosts()
