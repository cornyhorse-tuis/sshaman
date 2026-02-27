"""Add / edit host form screen."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from backend.host_entry import HostEntry


class HostFormScreen(ModalScreen[HostEntry | None]):
    """Modal form for adding or editing an SSH host.

    If ``host`` is provided the form is pre-filled for editing.
    Dismisses with a :class:`HostEntry` on save, or ``None`` on cancel.

    Args:
        host: Existing host to edit, or ``None`` for a new host.
        config_files: Available config.d filenames for the selector.
        default_config_file: Pre-selected config file name.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    HostFormScreen {
        align: center middle;
    }

    HostFormScreen > Vertical {
        width: 65;
        height: auto;
        max-height: 35;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    HostFormScreen > Vertical > Label {
        margin-top: 1;
    }

    HostFormScreen > Vertical > Input {
        margin-bottom: 0;
    }

    HostFormScreen > Vertical > .form-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    HostFormScreen > Vertical > .form-buttons > Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        host: Optional[HostEntry] = None,
        config_files: Optional[list[str]] = None,
        default_config_file: str = "sshaman-hosts",
    ) -> None:
        super().__init__()
        self._host = host
        self._config_files = config_files or [default_config_file]
        # Pick a valid default: prefer the caller's default, fall back to first.
        if default_config_file in self._config_files:
            self._default_config_file = default_config_file
        else:
            self._default_config_file = self._config_files[0]
        self._selected_config_file = self._default_config_file

    def compose(self) -> ComposeResult:
        """Build the form."""
        h = self._host
        with Vertical():
            yield Label(
                "[bold]Add Host[/bold]"
                if h is None
                else f"[bold]Edit Host: {h.name}[/bold]"
            )

            yield Label("Host alias:")
            yield Input(
                value=h.name if h else "",
                placeholder="e.g. web-prod",
                id="input-name",
                disabled=h is not None,  # Can't rename via edit
            )

            yield Label("HostName (IP / domain):")
            yield Input(
                value=h.hostname if h else "",
                placeholder="e.g. 192.168.1.100",
                id="input-hostname",
            )

            yield Label("User:")
            yield Input(
                value=h.user if h and h.user else "",
                placeholder="e.g. matt",
                id="input-user",
            )

            yield Label("Port:")
            yield Input(
                value=str(h.port) if h else "22",
                placeholder="22",
                id="input-port",
            )

            yield Label("IdentityFile:")
            yield Input(
                value=str(h.identity_file) if h and h.identity_file else "",
                placeholder="~/.ssh/id_rsa",
                id="input-identity-file",
            )

            if len(self._config_files) > 1:
                yield Label("Config file:")
                yield Select(
                    [(f, f) for f in self._config_files],
                    value=self._default_config_file,
                    id="select-config-file",
                )

            with Vertical(classes="form-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Track which config file is selected."""
        if event.select.id == "select-config-file" and event.value is not None:
            self._selected_config_file = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save / cancel."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return

        # Gather values
        name = self.query_one("#input-name", Input).value.strip()
        hostname = self.query_one("#input-hostname", Input).value.strip()
        user = self.query_one("#input-user", Input).value.strip() or None
        port_str = self.query_one("#input-port", Input).value.strip()
        identity = self.query_one("#input-identity-file", Input).value.strip()

        # Basic validation
        if not name:
            self.notify("Host alias is required.", severity="error")
            return
        if not hostname:
            self.notify("HostName is required.", severity="error")
            return

        try:
            port = int(port_str) if port_str else 22
        except ValueError:
            self.notify("Port must be a number.", severity="error")
            return

        try:
            entry = HostEntry(
                name=name,
                hostname=hostname,
                user=user,
                port=port,
                identity_file=Path(identity) if identity else None,
            )
        except Exception as exc:
            self.notify(f"Validation error: {exc}", severity="error")
            return

        # Stash config file choice on the entry for the caller to use
        entry._config_file = self._selected_config_file  # type: ignore[attr-defined]
        self.dismiss(entry)

    def action_cancel(self) -> None:
        """Escape key — cancel form."""
        self.dismiss(None)
