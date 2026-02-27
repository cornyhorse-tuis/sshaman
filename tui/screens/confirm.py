"""Confirmation dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """A modal yes/no confirmation dialog.

    Args:
        message: The question to display.
    """

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    ConfirmScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 12;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    ConfirmScreen > Vertical > Label {
        width: 100%;
        content-align: center middle;
        margin-bottom: 1;
    }

    ConfirmScreen > Vertical > Horizontal {
        width: 100%;
        height: auto;
        align: center middle;
    }

    ConfirmScreen > Vertical > Horizontal > Button {
        margin: 0 2;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Build the confirmation dialog."""
        with Vertical():
            yield Label(self._message)
            with Horizontal():
                yield Button("Yes", variant="error", id="confirm-yes")
                yield Button("No", variant="primary", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press — dismiss with True/False."""
        self.dismiss(event.button.id == "confirm-yes")
