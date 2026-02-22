"""Host detail screen — shows full info for a single host."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from backend.host_entry import HostEntry


class HostDetailScreen(ModalScreen[str | None]):
    """Display detailed information for a single SSH host.

    Dismisses with:
      - ``"ssh"`` if the user presses Connect
      - ``"sftp"`` if the user presses SFTP
      - ``None`` if the user presses Back
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("c", "do_connect", "SSH"),
        ("s", "do_sftp", "SFTP"),
    ]

    DEFAULT_CSS = """
    HostDetailScreen {
        align: center middle;
    }

    HostDetailScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 30;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    HostDetailScreen > Vertical > #detail-info {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    HostDetailScreen > Vertical > .detail-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    HostDetailScreen > Vertical > .detail-buttons > Button {
        margin: 0 1;
    }
    """

    def __init__(self, host: HostEntry) -> None:
        super().__init__()
        self._host = host

    def compose(self) -> ComposeResult:
        """Build the detail view."""
        h = self._host
        source = h.source_file.name if h.source_file else "unknown"
        lines = [
            f"[bold]Host:[/bold]          {h.name}",
            f"[bold]HostName:[/bold]      {h.hostname}",
            f"[bold]User:[/bold]          {h.user or '—'}",
            f"[bold]Port:[/bold]          {h.port}",
            f"[bold]IdentityFile:[/bold]  {h.identity_file or '—'}",
            f"[bold]ProxyJump:[/bold]     {h.proxy_jump or '—'}",
            f"[bold]ForwardAgent:[/bold]  {h.forward_agent if h.forward_agent is not None else '—'}",
        ]
        if h.local_forwards:
            lines.append(f"[bold]LocalForward:[/bold]  {', '.join(h.local_forwards)}")
        if h.extra_options:
            for k, v in h.extra_options.items():
                lines.append(f"[bold]{k.capitalize()}:[/bold]  {v}")
        lines.append(f"\n[dim]Source: {source}[/dim]")

        with Vertical():
            yield Static("\n".join(lines), id="detail-info")
            with Vertical(classes="detail-buttons"):
                yield Button("[c] Connect SSH", variant="primary", id="btn-ssh")
                yield Button("[s] Connect SFTP", variant="default", id="btn-sftp")
                yield Button("[Esc] Back", id="btn-back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-ssh":
            self.dismiss("ssh")
        elif event.button.id == "btn-sftp":
            self.dismiss("sftp")
        else:
            self.dismiss(None)

    def action_go_back(self) -> None:
        """Escape key — go back."""
        self.dismiss(None)

    def action_do_connect(self) -> None:
        """Key 'c' — connect via SSH."""
        self.dismiss("ssh")

    def action_do_sftp(self) -> None:
        """Key 's' — connect via SFTP."""
        self.dismiss("sftp")
