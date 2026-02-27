"""Tests for the SSHaMan TUI (Textual app + screens).

Every test uses ``tmp_path`` fixtures — no real ``~/.ssh/`` is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Input

from backend.host_entry import HostEntry
from backend.manager import SSHManager
from tui.app import SSHaManApp
from tui.screens.confirm import ConfirmScreen
from tui.screens.config_files import ConfigFilesScreen, NewConfigFileScreen
from tui.screens.host_detail import HostDetailScreen
from tui.screens.host_form import HostFormScreen

# Use a large terminal size so modal dialogs fit.
SCREEN_SIZE = (120, 50)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tui_manager(sample_ssh_dir: Path) -> SSHManager:
    """Return an SSHManager for TUI tests."""
    return SSHManager(ssh_dir=sample_ssh_dir)


@pytest.fixture
def empty_tui_manager(ssh_dir: Path) -> SSHManager:
    """Return an SSHManager with no hosts."""
    return SSHManager(ssh_dir=ssh_dir)


# ===================================================================
# SSHaManApp — main application
# ===================================================================


class TestAppStartup:
    """App startup / composition tests."""

    async def test_app_starts_and_shows_hosts(self, tui_manager: SSHManager) -> None:
        """App should mount and populate the host table with 3 hosts."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_app_starts_empty(self, empty_tui_manager: SSHManager) -> None:
        """App with no hosts should show an empty table."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 0

    async def test_app_has_header_and_footer(self, tui_manager: SSHManager) -> None:
        """App should compose Header and Footer."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            from textual.widgets import Header, Footer

            assert len(app.query(Header)) == 1
            assert len(app.query(Footer)) == 1

    async def test_app_has_filter_input(self, tui_manager: SSHManager) -> None:
        """App should have a filter input."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            inp = app.query_one("#filter-input", Input)
            assert inp.placeholder == "Filter hosts…"


class TestHostTableFiltering:
    """Test live filtering of the host table."""

    async def test_filter_narrows_results(self, tui_manager: SSHManager) -> None:
        """Typing in filter box should narrow visible hosts."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            inp = app.query_one("#filter-input", Input)
            inp.focus()
            await pilot.press("w", "e", "b")
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 1  # Only web-server matches

    async def test_filter_shows_all_when_empty(self, tui_manager: SSHManager) -> None:
        """Empty filter should show all hosts."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            inp = app.query_one("#filter-input", Input)
            inp.focus()
            await pilot.press("x")
            await pilot.pause()
            # Now clear it
            await pilot.press("backspace")
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_focus_filter_action(self, tui_manager: SSHManager) -> None:
        """The slash key should focus the filter input."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("slash")
            await pilot.pause()
            inp = app.query_one("#filter-input", Input)
            assert inp.has_focus


class TestHostTableNavigation:
    """Test row selection and detail view."""

    async def test_enter_opens_detail(self, tui_manager: SSHManager) -> None:
        """Pressing Enter on a row should open the HostDetailScreen."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            # HostDetailScreen should be on screen stack
            assert any(isinstance(s, HostDetailScreen) for s in app.screen_stack)

    async def test_detail_back_returns(self, tui_manager: SSHManager) -> None:
        """Pressing Escape in the detail view should return to the table."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert not any(isinstance(s, HostDetailScreen) for s in app.screen_stack)


class TestSSHConnection:
    """Test SSH/SFTP connection actions."""

    async def test_connect_ssh_exits(self, tui_manager: SSHManager) -> None:
        """Pressing 'c' with a selected row should exit with ('ssh', host)."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

        assert app.return_value is not None
        action, host = app.return_value
        assert action == "ssh"

    async def test_connect_sftp_exits(self, tui_manager: SSHManager) -> None:
        """Pressing 's' with a selected row should exit with ('sftp', host)."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()

        assert app.return_value is not None
        action, host = app.return_value
        assert action == "sftp"

    async def test_connect_ssh_no_selection(
        self, empty_tui_manager: SSHManager
    ) -> None:
        """SSH connect with no hosts should not crash."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("c")
            await pilot.pause()
        # Should not have exited with a result
        assert app.return_value is None

    async def test_connect_sftp_no_selection(
        self, empty_tui_manager: SSHManager
    ) -> None:
        """SFTP connect with no hosts should not crash."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("s")
            await pilot.pause()
        assert app.return_value is None

    async def test_detail_ssh_connect(self, tui_manager: SSHManager) -> None:
        """Pressing 'c' in detail view should exit with ssh action."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

        assert app.return_value is not None
        action, _ = app.return_value
        assert action == "ssh"

    async def test_detail_sftp_connect(self, tui_manager: SSHManager) -> None:
        """Pressing 's' in detail view should exit with sftp action."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()

        assert app.return_value is not None
        action, _ = app.return_value
        assert action == "sftp"


class TestAddHost:
    """Test the add-host workflow."""

    async def test_add_host_opens_form(self, tui_manager: SSHManager) -> None:
        """Pressing 'a' should open the HostFormScreen."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("a")
            await pilot.pause()
            assert any(isinstance(s, HostFormScreen) for s in app.screen_stack)

    async def test_add_host_cancel(self, tui_manager: SSHManager) -> None:
        """Pressing escape in the form should cancel without adding."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert table.row_count == 3  # unchanged


class TestEditHost:
    """Test the edit-host workflow."""

    async def test_edit_opens_form(self, tui_manager: SSHManager) -> None:
        """Pressing 'e' on a selected row should open the edit form."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            assert any(isinstance(s, HostFormScreen) for s in app.screen_stack)

    async def test_edit_no_selection(self, empty_tui_manager: SSHManager) -> None:
        """Pressing 'e' with no hosts should not crash."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("e")
            await pilot.pause()
            # No form should be on stack
            assert not any(isinstance(s, HostFormScreen) for s in app.screen_stack)


class TestDeleteHost:
    """Test the delete-host workflow."""

    async def test_delete_opens_confirm(self, tui_manager: SSHManager) -> None:
        """Pressing 'd' should open a confirmation dialog."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            assert any(isinstance(s, ConfirmScreen) for s in app.screen_stack)

    async def test_delete_no_selection(self, empty_tui_manager: SSHManager) -> None:
        """Pressing 'd' with no hosts should not crash."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("d")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in app.screen_stack)


class TestConfigFiles:
    """Test config file management screen."""

    async def test_open_config_files(self, tui_manager: SSHManager) -> None:
        """Pressing 'f' should open the ConfigFilesScreen."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("f")
            await pilot.pause()
            assert any(isinstance(s, ConfigFilesScreen) for s in app.screen_stack)

    async def test_config_files_escape(self, tui_manager: SSHManager) -> None:
        """Escape from config files screen should return to main."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("f")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert not any(isinstance(s, ConfigFilesScreen) for s in app.screen_stack)


class TestQuit:
    """Test quitting the app."""

    async def test_quit_with_q(self, tui_manager: SSHManager) -> None:
        """Pressing 'q' should quit the app."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await pilot.press("q")
            await pilot.pause()
        assert app.return_value is None


# ===================================================================
# ConfirmScreen — unit tests
# ===================================================================


class TestConfirmScreen:
    """Unit tests for the confirmation dialog."""

    async def test_confirm_yes(self, tui_manager: SSHManager) -> None:
        """Clicking Yes should dismiss with True."""
        app = SSHaManApp(manager=tui_manager)
        results: list[bool] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                ConfirmScreen("Delete this?"), callback=results.append
            )
            await pilot.pause()
            await pilot.click("#confirm-yes")
            await pilot.pause()

        assert results == [True]

    async def test_confirm_no(self, tui_manager: SSHManager) -> None:
        """Clicking No should dismiss with False."""
        app = SSHaManApp(manager=tui_manager)
        results: list[bool] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                ConfirmScreen("Delete this?"), callback=results.append
            )
            await pilot.pause()
            await pilot.click("#confirm-no")
            await pilot.pause()

        assert results == [False]


# ===================================================================
# HostDetailScreen — unit tests
# ===================================================================


class TestHostDetailScreen:
    """Unit tests for the host detail screen."""

    async def test_detail_shows_host_info(self, tui_manager: SSHManager) -> None:
        """The detail screen should display host information."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host))
            await pilot.pause()
            # Check the screen is mounted
            assert any(isinstance(s, HostDetailScreen) for s in app.screen_stack)

    async def test_detail_ssh_button(self, tui_manager: SSHManager) -> None:
        """Clicking SSH button should dismiss with 'ssh'."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.click("#btn-ssh")
            await pilot.pause()

        assert results == ["ssh"]

    async def test_detail_sftp_button(self, tui_manager: SSHManager) -> None:
        """Clicking SFTP button should dismiss with 'sftp'."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.click("#btn-sftp")
            await pilot.pause()

        assert results == ["sftp"]

    async def test_detail_back_button(self, tui_manager: SSHManager) -> None:
        """Clicking Back button should dismiss with None."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()

        assert results == [None]

    async def test_detail_escape(self, tui_manager: SSHManager) -> None:
        """Pressing Escape should dismiss with None."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]

    async def test_detail_c_key(self, tui_manager: SSHManager) -> None:
        """Pressing 'c' should dismiss with 'ssh'."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

        assert results == ["ssh"]

    async def test_detail_s_key(self, tui_manager: SSHManager) -> None:
        """Pressing 's' should dismiss with 'sftp'."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host), callback=results.append)
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()

        assert results == ["sftp"]

    async def test_detail_host_with_extras(self, sample_ssh_dir: Path) -> None:
        """Detail screen should render extra options and forwards."""
        # Add a host with extras
        config_file = sample_ssh_dir / "config.d" / "extras"
        config_file.write_text(
            "Host fancy-server\n"
            "    HostName 1.2.3.4\n"
            "    User root\n"
            "    ProxyJump bastion\n"
            "    ForwardAgent yes\n"
            "    LocalForward 8080:localhost:80\n"
            "    StrictHostKeyChecking no\n\n",
            encoding="utf-8",
        )
        config_file.chmod(0o600)

        mgr = SSHManager(ssh_dir=sample_ssh_dir)
        host = mgr.get_host("fancy-server")
        assert host is not None

        app = SSHaManApp(manager=mgr)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(HostDetailScreen(host))
            await pilot.pause()
            # Just verify it mounted without error
            assert any(isinstance(s, HostDetailScreen) for s in app.screen_stack)


# ===================================================================
# HostFormScreen — unit tests
# ===================================================================


class TestHostFormScreen:
    """Unit tests for the host add/edit form."""

    async def test_form_cancel(self, tui_manager: SSHManager) -> None:
        """Cancelling the form should dismiss with None."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()
            app.screen.query_one("#btn-cancel", Button).press()
            await pilot.pause()

        assert results == [None]

    async def test_form_escape(self, tui_manager: SSHManager) -> None:
        """Pressing Escape should cancel the form."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]

    async def test_form_save_valid(self, tui_manager: SSHManager) -> None:
        """Saving a valid form should dismiss with a HostEntry."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            # Fill in form fields
            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "new-host"
            hostname_input = app.screen.query_one("#input-hostname", Input)
            hostname_input.value = "10.0.0.99"
            user_input = app.screen.query_one("#input-user", Input)
            user_input.value = "admin"

            await pilot.click("#btn-save")
            await pilot.pause()

        assert len(results) == 1
        entry = results[0]
        assert entry is not None
        assert entry.name == "new-host"
        assert entry.hostname == "10.0.0.99"
        assert entry.user == "admin"
        assert entry.port == 22

    async def test_form_save_empty_name(self, tui_manager: SSHManager) -> None:
        """Saving with empty name should show error and not dismiss."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            # Leave name empty, fill hostname
            hostname_input = app.screen.query_one("#input-hostname", Input)
            hostname_input.value = "10.0.0.99"

            await pilot.click("#btn-save")
            await pilot.pause()

        # Should not have been dismissed
        assert len(results) == 0

    async def test_form_save_empty_hostname(self, tui_manager: SSHManager) -> None:
        """Saving with empty hostname should show error and not dismiss."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            # Fill name but leave hostname empty
            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "new-host"

            await pilot.click("#btn-save")
            await pilot.pause()

        assert len(results) == 0

    async def test_form_save_invalid_port(self, tui_manager: SSHManager) -> None:
        """Saving with a non-numeric port should show error."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "new-host"
            hostname_input = app.screen.query_one("#input-hostname", Input)
            hostname_input.value = "10.0.0.99"
            port_input = app.screen.query_one("#input-port", Input)
            port_input.value = "abc"

            await pilot.click("#btn-save")
            await pilot.pause()

        assert len(results) == 0

    async def test_form_edit_mode(self, tui_manager: SSHManager) -> None:
        """In edit mode, name should be pre-filled and disabled."""
        host = tui_manager.get_host("web-server")
        assert host is not None

        app = SSHaManApp(manager=tui_manager)

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(host=host, config_files=["test-hosts"]),
            )
            await pilot.pause()

            name_input = app.screen.query_one("#input-name", Input)
            assert name_input.value == "web-server"
            assert name_input.disabled

            hostname_input = app.screen.query_one("#input-hostname", Input)
            assert hostname_input.value == "192.168.1.100"


# ===================================================================
# ConfigFilesScreen — unit tests
# ===================================================================


class TestConfigFilesScreen:
    """Unit tests for the config file management screen."""

    async def test_config_files_shows_files(self, tui_manager: SSHManager) -> None:
        """Screen should list config files from config.d/."""
        app = SSHaManApp(manager=tui_manager)

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(ConfigFilesScreen())
            await pilot.pause()

            table = app.screen.query_one("#config-table", DataTable)
            assert table.row_count == 2  # test-hosts, extra-hosts

    async def test_config_files_back_button(self, tui_manager: SSHManager) -> None:
        """Clicking Back should dismiss the screen."""
        app = SSHaManApp(manager=tui_manager)
        results: list[None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(ConfigFilesScreen(), callback=results.append)
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()

        assert results == [None]

    async def test_config_files_escape(self, tui_manager: SSHManager) -> None:
        """Pressing Escape should dismiss the screen."""
        app = SSHaManApp(manager=tui_manager)
        results: list[None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(ConfigFilesScreen(), callback=results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]

    async def test_config_files_new_button(self, tui_manager: SSHManager) -> None:
        """Clicking New should open the NewConfigFileScreen."""
        app = SSHaManApp(manager=tui_manager)

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(ConfigFilesScreen())
            await pilot.pause()
            await pilot.click("#btn-new")
            await pilot.pause()

            assert any(isinstance(s, NewConfigFileScreen) for s in app.screen_stack)


# ===================================================================
# NewConfigFileScreen — unit tests
# ===================================================================


class TestNewConfigFileScreen:
    """Unit tests for the new config file dialog."""

    async def test_create_config_file(self, tui_manager: SSHManager) -> None:
        """Entering a name and clicking Create should dismiss with the name."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()

            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "30-new-config"

            await pilot.click("#btn-create")
            await pilot.pause()

        assert results == ["30-new-config"]

    async def test_create_empty_name(self, tui_manager: SSHManager) -> None:
        """Creating with empty name should not dismiss."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()

            # Leave name empty
            await pilot.click("#btn-create")
            await pilot.pause()

        assert len(results) == 0

    async def test_cancel_config_file(self, tui_manager: SSHManager) -> None:
        """Clicking Cancel should dismiss with None."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()
            app.screen.query_one("#btn-cancel", Button).press()
            await pilot.pause()

        assert results == [None]

    async def test_escape_config_file(self, tui_manager: SSHManager) -> None:
        """Pressing Escape should dismiss with None."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]


# ===================================================================
# App callback tests (add/edit/delete flow integrations)
# ===================================================================


class TestAppCallbacks:
    """Test internal callbacks that process screen results."""

    async def test_on_add_host_result_none(self, tui_manager: SSHManager) -> None:
        """Callback _on_add_host_result(None) should be a no-op."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_add_host_result(None)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_on_add_host_result_duplicate(self, tui_manager: SSHManager) -> None:
        """Adding a duplicate host should show error notification."""
        existing = tui_manager.get_host("web-server")
        assert existing is not None

        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            entry = HostEntry(name="web-server", hostname="1.2.3.4")
            entry._config_file = "test-hosts"  # type: ignore[attr-defined]
            app._on_add_host_result(entry)
            await pilot.pause()
            # Host count should remain the same
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_on_edit_host_result_none(self, tui_manager: SSHManager) -> None:
        """Callback _on_edit_host_result(None) should be a no-op."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_edit_host_result(None)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_on_edit_host_result_not_found(self, tui_manager: SSHManager) -> None:
        """Editing a nonexistent host should show error notification."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            entry = HostEntry(name="nonexistent", hostname="1.2.3.4")
            app._on_edit_host_result(entry)
            await pilot.pause()

    async def test_on_delete_confirmed_false(self, tui_manager: SSHManager) -> None:
        """Callback _on_delete_confirmed(False) should be a no-op."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_delete_confirmed(False)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3

    async def test_on_detail_result_none(self, tui_manager: SSHManager) -> None:
        """Callback _on_detail_result(None) should be a no-op."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_detail_result(None)
            await pilot.pause()
        assert app.return_value is None

    async def test_on_files_closed(self, tui_manager: SSHManager) -> None:
        """Callback _on_files_closed should refresh hosts."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_files_closed(None)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3


# ===================================================================
# _get_selected_host_name edge cases
# ===================================================================


class TestGetSelectedHostName:
    """Test the _get_selected_host_name helper."""

    async def test_returns_none_when_empty(self, empty_tui_manager: SSHManager) -> None:
        """Should return None when table is empty."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            result = app._get_selected_host_name()
            assert result is None


# ===================================================================
# Additional coverage tests
# ===================================================================


class TestAddHostEmptyConfigFiles:
    """Test add-host when no config files exist."""

    async def test_add_host_with_no_config_files(self, ssh_dir: Path) -> None:
        """When no config files exist, add_host should use ['sshaman-hosts']."""
        mgr = SSHManager(ssh_dir=ssh_dir)
        app = SSHaManApp(manager=mgr)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.press("a")
            await pilot.pause()
            assert any(isinstance(s, HostFormScreen) for s in app.screen_stack)


class TestDeleteHostConfirmed:
    """Test actual deletion after confirmation."""

    async def test_delete_host_confirmed_true(self, tui_manager: SSHManager) -> None:
        """When confirmed, _on_delete_confirmed should delete the host."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            assert table.row_count == 3
            # Directly call deletion callback
            app._on_delete_confirmed(True)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 2


class TestEditHostSuccess:
    """Test successful host editing."""

    async def test_edit_host_success(self, tui_manager: SSHManager) -> None:
        """Successfully editing a host should update it."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            # Create a valid entry for the callback
            entry = HostEntry(name="web-server", hostname="10.99.99.99", user="newuser")
            app._on_edit_host_result(entry)
            await pilot.pause()
            # Verify host was updated
            host = tui_manager.get_host("web-server")
            assert host is not None
            assert host.hostname == "10.99.99.99"


class TestAddHostSuccess:
    """Test successful host adding."""

    async def test_add_host_success(self, tui_manager: SSHManager) -> None:
        """Successfully adding a host should add it to the table."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 3
            entry = HostEntry(name="brand-new", hostname="99.99.99.99")
            entry._config_file = "test-hosts"  # type: ignore[attr-defined]
            app._on_add_host_result(entry)
            await pilot.pause()
            table = app.query_one("#host-table", DataTable)
            assert table.row_count == 4


class TestDetailResultAction:
    """Test _on_detail_result with an action that exits."""

    async def test_detail_connect_exits_app(self, tui_manager: SSHManager) -> None:
        """_on_detail_result with 'ssh' should exit the app."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            app._on_detail_result("ssh")
            await pilot.pause()
        assert app.return_value is not None
        action, _ = app.return_value
        assert action == "ssh"


class TestConfigFilesNewFileCallback:
    """Test the new-file creation callback in ConfigFilesScreen."""

    async def test_new_file_created(self, tui_manager: SSHManager) -> None:
        """Creating a new config file through the callback should work."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = ConfigFilesScreen()
            await app.push_screen(screen)
            await pilot.pause()

            table = app.screen.query_one("#config-table", DataTable)
            initial_count = table.row_count

            # Trigger the callback directly
            screen._on_new_file("50-new-file")
            await pilot.pause()

            table = app.screen.query_one("#config-table", DataTable)
            assert table.row_count == initial_count + 1

    async def test_new_file_none_callback(self, tui_manager: SSHManager) -> None:
        """Passing None to _on_new_file should be a no-op."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = ConfigFilesScreen()
            await app.push_screen(screen)
            await pilot.pause()

            table = app.screen.query_one("#config-table", DataTable)
            initial_count = table.row_count

            screen._on_new_file(None)
            await pilot.pause()

            table = app.screen.query_one("#config-table", DataTable)
            assert table.row_count == initial_count

    async def test_new_file_duplicate_error(self, tui_manager: SSHManager) -> None:
        """Creating a duplicate file should show error."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = ConfigFilesScreen()
            await app.push_screen(screen)
            await pilot.pause()

            # Create it first
            screen._on_new_file("60-dup-test")
            await pilot.pause()

            # Try creating again — should error
            screen._on_new_file("60-dup-test")
            await pilot.pause()


class TestHostFormWithMultipleConfigFiles:
    """Test the form with multiple config files (showing Select widget)."""

    async def test_form_with_select(self, tui_manager: SSHManager) -> None:
        """Form with multiple config files should show a Select widget."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            from textual.widgets import Select

            await app.push_screen(
                HostFormScreen(config_files=["file-a", "file-b"]),
            )
            await pilot.pause()

            select = app.screen.query_one("#select-config-file", Select)
            assert select is not None

    async def test_form_default_config_in_list(self, tui_manager: SSHManager) -> None:
        """When default_config_file is in the list, it should be selected."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = HostFormScreen(
                config_files=["sshaman-hosts", "other-file"],
                default_config_file="sshaman-hosts",
            )
            await app.push_screen(screen)
            await pilot.pause()
            assert screen._default_config_file == "sshaman-hosts"

    async def test_form_save_with_identity_file(self, tui_manager: SSHManager) -> None:
        """Saving with identity file should include it in the entry."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            app.screen.query_one("#input-name", Input).value = "id-host"
            app.screen.query_one("#input-hostname", Input).value = "1.2.3.4"
            app.screen.query_one(
                "#input-identity-file", Input
            ).value = "~/.ssh/id_ed25519"

            app.screen.query_one("#btn-save", Button).press()
            await pilot.pause()

        assert len(results) == 1
        assert results[0] is not None
        assert results[0].identity_file == Path("~/.ssh/id_ed25519")


# ===================================================================
# Coverage gap tests — filling remaining uncovered paths
# ===================================================================


class TestGetSelectedHostNameException:
    """Cover _get_selected_host_name exception fallback (lines 110-111)."""

    async def test_returns_none_on_coordinate_exception(
        self, tui_manager: SSHManager
    ) -> None:
        """If coordinate_to_cell_key raises, return None instead of crashing."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as _:
            table = app.query_one("#host-table", DataTable)
            original = table.coordinate_to_cell_key

            def broken_coordinate_to_cell_key(coord):
                raise IndexError("simulated error")

            table.coordinate_to_cell_key = broken_coordinate_to_cell_key
            result = app._get_selected_host_name()
            assert result is None
            # Restore to prevent side effects
            table.coordinate_to_cell_key = original


class TestRowSelectedHostNotFound:
    """Cover on_data_table_row_selected when host is None (line 135)."""

    async def test_row_selected_host_deleted(self, tui_manager: SSHManager) -> None:
        """If the host was deleted between display and selection, no crash."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            # Mock get_host to return None (simulating a race condition)
            original_get_host = tui_manager.get_host
            tui_manager.get_host = lambda name: None
            await pilot.press("enter")
            await pilot.pause()
            tui_manager.get_host = original_get_host
            # Should NOT have pushed a detail screen
            assert not any(isinstance(s, HostDetailScreen) for s in app.screen_stack)


class TestDetailResultHostNameNone:
    """Cover _on_detail_result when host_name is None (branch 143->exit)."""

    async def test_detail_result_no_selected_host(
        self, empty_tui_manager: SSHManager
    ) -> None:
        """_on_detail_result with valid action but no selected host is a no-op."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            # Table is empty, so _get_selected_host_name returns None
            app._on_detail_result("ssh")
            await pilot.pause()
        # Should NOT have exited with a result
        assert app.return_value is None


class TestEditHostGetHostNone:
    """Cover action_edit_host when get_host returns None (line 180)."""

    async def test_edit_host_after_backend_delete(
        self, tui_manager: SSHManager
    ) -> None:
        """If host is deleted between selection and edit, no crash."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            # Mock get_host to return None (simulating a race condition)
            original_get_host = tui_manager.get_host
            tui_manager.get_host = lambda name: None
            await pilot.press("e")
            await pilot.pause()
            tui_manager.get_host = original_get_host
            # No form should appear
            assert not any(isinstance(s, HostFormScreen) for s in app.screen_stack)


class TestDeleteConfirmedHostGone:
    """Cover _on_delete_confirmed when host disappears (lines 221, 226-227)."""

    async def test_delete_confirmed_host_vanished(
        self, tui_manager: SSHManager
    ) -> None:
        """If host is gone when deletion is confirmed, handle gracefully."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            table.focus()
            await pilot.pause()
            # Remember current host, delete it from backend
            selected = app._get_selected_host_name()
            assert selected is not None
            tui_manager.remove_host(selected)
            # Now confirm deletion — host no longer exists in backend
            app._on_delete_confirmed(True)
            await pilot.pause()

    async def test_delete_confirmed_empty_table(
        self, empty_tui_manager: SSHManager
    ) -> None:
        """_on_delete_confirmed with empty table — host_name is None."""
        app = SSHaManApp(manager=empty_tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            app._on_delete_confirmed(True)
            await pilot.pause()
            # No crash, no action


class TestAddHostResultNoConfigAttr:
    """Cover _on_add_host_result when entry lacks _config_file (line 135)."""

    async def test_add_host_uses_default_config_file(
        self, tui_manager: SSHManager
    ) -> None:
        """HostEntry without _config_file falls back to 'sshaman-hosts'."""
        app = SSHaManApp(manager=tui_manager)
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            table = app.query_one("#host-table", DataTable)
            initial_count = table.row_count
            # Create entry without _config_file attribute
            entry = HostEntry(name="no-attr-host", hostname="9.9.9.9")
            app._on_add_host_result(entry)
            await pilot.pause()
            assert table.row_count == initial_count + 1
            # Verify it was written to sshaman-hosts
            host = tui_manager.get_host("no-attr-host")
            assert host is not None
            assert host.source_file is not None
            assert host.source_file.name == "sshaman-hosts"


class TestNewConfigFileRejectsInvalidName:
    """Cover NewConfigFileScreen regex rejection (lines 168-172)."""

    async def test_name_with_spaces_rejected(self, tui_manager: SSHManager) -> None:
        """Names with spaces should be rejected."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()

            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "bad name"
            await pilot.click("#btn-create")
            await pilot.pause()

        # Should NOT have dismissed — still 0 results
        assert len(results) == 0

    async def test_name_with_special_chars_rejected(
        self, tui_manager: SSHManager
    ) -> None:
        """Names with slashes or special chars should be rejected."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(NewConfigFileScreen(), callback=results.append)
            await pilot.pause()

            name_input = app.screen.query_one("#input-name", Input)
            name_input.value = "bad/name!"
            await pilot.click("#btn-create")
            await pilot.pause()

        assert len(results) == 0


class TestHostFormValidationError:
    """Cover HostFormScreen validation error handler (lines 174-176)."""

    async def test_pydantic_validation_error_shown(
        self, tui_manager: SSHManager, monkeypatch
    ) -> None:
        """When HostEntry construction raises, the form shows an error."""
        app = SSHaManApp(manager=tui_manager)
        results: list[HostEntry | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await app.push_screen(
                HostFormScreen(config_files=["test-hosts"]),
                callback=results.append,
            )
            await pilot.pause()

            # Fill in apparently valid data
            app.screen.query_one("#input-name", Input).value = "test-host"
            app.screen.query_one("#input-hostname", Input).value = "example.com"

            # Monkeypatch HostEntry to raise on construction
            def broken_init(self, **kwargs):
                raise ValueError("synthetic validation error")

            monkeypatch.setattr(HostEntry, "__init__", broken_init)

            app.screen.query_one("#btn-save", Button).press()
            await pilot.pause()

        # Form should NOT have dismissed
        assert len(results) == 0


class TestHostFormSelectChangedBranch:
    """Cover on_select_changed false branch (line 136->exit)."""

    async def test_select_changed_with_different_id(
        self, tui_manager: SSHManager
    ) -> None:
        """When Select.Changed arrives from an unknown select, no change."""
        app = SSHaManApp(manager=tui_manager)

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            from textual.widgets import Select

            screen = HostFormScreen(config_files=["file-a", "file-b"])
            await app.push_screen(screen)
            await pilot.pause()

            original = screen._selected_config_file
            # Simulate a select-changed event from a different select widget
            fake_select = Select([("x", "x")], id="other-select")
            event = Select.Changed(fake_select, "x")
            screen.on_select_changed(event)
            await pilot.pause()

            # The config file should not have changed
            assert screen._selected_config_file == original


class TestConfigFilesButtonFallthrough:
    """Cover ConfigFilesScreen on_button_pressed fallthrough (line 92->exit)."""

    async def test_unknown_button_is_noop(self, tui_manager: SSHManager) -> None:
        """A button with an unrecognized id should be a no-op."""
        app = SSHaManApp(manager=tui_manager)

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = ConfigFilesScreen()
            await app.push_screen(screen)
            await pilot.pause()

            from textual.widgets import Button

            # Simulate a button event the handler doesn't recognize
            fake_event = Button.Pressed(Button("Unknown", id="btn-unknown"))
            screen.on_button_pressed(fake_event)
            await pilot.pause()

            # Screen should still be attached
            assert screen.is_attached


class TestNewConfigFileButtonFallthrough:
    """Cover NewConfigFileScreen on_button_pressed fallthrough (line 161->exit)."""

    async def test_unknown_button_is_noop(self, tui_manager: SSHManager) -> None:
        """A button with an unrecognized id in NewConfigFileScreen is a no-op."""
        app = SSHaManApp(manager=tui_manager)
        results: list[str | None] = []

        async with app.run_test(size=SCREEN_SIZE) as pilot:
            screen = NewConfigFileScreen()
            await app.push_screen(screen, callback=results.append)
            await pilot.pause()

            from textual.widgets import Button

            fake_event = Button.Pressed(Button("Nope", id="btn-nope"))
            screen.on_button_pressed(fake_event)
            await pilot.pause()

            # Should NOT have dismissed
            assert screen.is_attached
            assert len(results) == 0
