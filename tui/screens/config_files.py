"""Config file management screen."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label

from backend.ssh_config import SSHConfigError


class ConfigFilesScreen(ModalScreen[None]):
    """Manage ``config.d/`` files — list, create, delete.

    Always dismisses with ``None``.
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("n", "new_file", "New"),
    ]

    DEFAULT_CSS = """
    ConfigFilesScreen {
        align: center middle;
    }

    ConfigFilesScreen > Vertical {
        width: 65;
        height: auto;
        max-height: 25;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    ConfigFilesScreen > Vertical > DataTable {
        height: auto;
        max-height: 14;
        margin-bottom: 1;
    }

    ConfigFilesScreen > Vertical > .cfg-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    ConfigFilesScreen > Vertical > .cfg-buttons > Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Build the config file list."""
        with Vertical():
            yield Label("[bold]Config Files[/bold]  (~/.ssh/config.d/)")
            yield DataTable(id="config-table")
            with Vertical(classes="cfg-buttons"):
                yield Button("[n] New file", variant="primary", id="btn-new")
                yield Button("[Esc] Back", id="btn-back")

    def on_mount(self) -> None:
        """Populate the table on mount."""
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Re-read config files and repopulate the table."""
        table = self.query_one("#config-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Filename", "Hosts")

        manager = self.app.manager  # type: ignore[attr-defined]
        files = manager.list_config_files()
        all_hosts = manager.list_hosts()

        for path in files:
            count = sum(
                1 for h in all_hosts
                if h.source_file and h.source_file.name == path.name
            )
            table.add_row(path.name, str(count), key=path.name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-back":
            self.dismiss(None)
        elif event.button.id == "btn-new":
            self.action_new_file()

    def action_go_back(self) -> None:
        """Escape — dismiss."""
        self.dismiss(None)

    def action_new_file(self) -> None:
        """Prompt for a new config file name."""
        self.app.push_screen(NewConfigFileScreen(), callback=self._on_new_file)

    def _on_new_file(self, name: str | None) -> None:
        """Callback after the new-file dialog returns."""
        if name is None:
            return
        manager = self.app.manager  # type: ignore[attr-defined]
        try:
            manager.create_config_file(name)
            self.notify(f"Created {name}")
            self._refresh_table()
        except SSHConfigError as exc:
            self.notify(str(exc), severity="error")


class NewConfigFileScreen(ModalScreen[str | None]):
    """Small dialog that asks for a new config file name."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    NewConfigFileScreen {
        align: center middle;
    }

    NewConfigFileScreen > Vertical {
        width: 50;
        height: auto;
        max-height: 10;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    NewConfigFileScreen > Vertical > Input {
        margin-bottom: 1;
    }

    NewConfigFileScreen > Vertical > .ncf-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    NewConfigFileScreen > Vertical > .ncf-buttons > Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Config file name:")
            yield Input(placeholder="e.g. 10-work-servers", id="input-name")
            with Vertical(classes="ncf-buttons"):
                yield Button("Create", variant="primary", id="btn-create")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            value = self.query_one("#input-name", Input).value.strip()
            if not value:
                self.notify("Name cannot be empty.", severity="error")
                return
            self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)
