"""Tests for the SSHaMan CLI.

All tests use CliRunner with --ssh-dir pointing to tmp_path fixtures —
never the real ~/.ssh directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from backend.manager import SSHManager
from cli.sshaman_cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def invoke(runner: CliRunner, ssh_dir: Path, *args: str, input: str | None = None):
    """Invoke the CLI with --ssh-dir set to the test directory."""
    return runner.invoke(cli, ["--ssh-dir", str(ssh_dir), *args], input=input, catch_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def populated_ssh_dir(ssh_dir: Path) -> Path:
    """An ssh_dir with one config file containing two hosts."""
    mgr = SSHManager(ssh_dir=ssh_dir)
    from backend.host_entry import HostEntry

    mgr.add_host(
        HostEntry(name="web-server", hostname="10.0.0.1", user="admin", port=22),
        config_file="test-hosts",
    )
    mgr.add_host(
        HostEntry(name="db-server", hostname="10.0.0.2", user="postgres", port=5432),
        config_file="test-hosts",
    )
    return ssh_dir


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

class TestListCommand:
    def test_list_shows_all_hosts(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "list")
        assert result.exit_code == 0
        assert "web-server" in result.output
        assert "db-server" in result.output

    def test_list_empty(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "list")
        assert result.exit_code == 0
        assert "No hosts found" in result.output

    def test_list_with_filter_match(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "list", "--filter", "web")
        assert result.exit_code == 0
        assert "web-server" in result.output
        assert "db-server" not in result.output

    def test_list_filter_by_hostname(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "list", "-f", "10.0.0.2")
        assert result.exit_code == 0
        assert "db-server" in result.output
        assert "web-server" not in result.output

    def test_list_filter_no_match(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "list", "--filter", "nonexistent")
        assert result.exit_code == 0
        assert "No hosts found" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

class TestShowCommand:
    def test_show_existing_host(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "show", "web-server")
        assert result.exit_code == 0
        assert "web-server" in result.output
        assert "10.0.0.1" in result.output
        assert "admin" in result.output

    def test_show_nonexistent_host(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "show", "ghost")
        assert result.exit_code == 1

    def test_show_host_with_optional_fields(self, runner, ssh_dir):
        from backend.host_entry import HostEntry
        from backend.manager import SSHManager as Mgr

        mgr = Mgr(ssh_dir=ssh_dir)
        mgr.add_host(
            HostEntry(
                name="complex",
                hostname="192.168.1.50",
                user="ubuntu",
                port=2222,
                identity_file=Path("~/.ssh/id_rsa"),
                proxy_jump="bastion",
                forward_agent=True,
                local_forwards=["8080:localhost:80"],
                extra_options={"serveraliveinterval": "60"},
            ),
            config_file="test-hosts",
        )
        result = invoke(runner, ssh_dir, "show", "complex")
        assert result.exit_code == 0
        assert "192.168.1.50" in result.output
        assert "ubuntu" in result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

class TestAddCommand:
    def test_add_host_minimal(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "add", "new-host", "--hostname", "192.168.1.1")
        assert result.exit_code == 0
        assert "new-host" in result.output

        mgr = SSHManager(ssh_dir=ssh_dir)
        assert mgr.get_host("new-host") is not None

    def test_add_host_all_options(self, runner, ssh_dir):
        result = invoke(
            runner, ssh_dir,
            "add", "full-host",
            "--hostname", "10.10.0.1",
            "--user", "deploy",
            "--port", "2222",
            "--identity-file", "~/.ssh/deploy_key",
            "--config-file", "custom-file",
        )
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=ssh_dir)
        host = mgr.get_host("full-host")
        assert host is not None
        assert host.user == "deploy"
        assert host.port == 2222

    def test_add_duplicate_host_fails(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "add", "web-server", "--hostname", "10.0.0.99")
        assert result.exit_code == 1

    def test_add_host_custom_config_file(self, runner, ssh_dir):
        result = invoke(
            runner, ssh_dir,
            "add", "work-server",
            "--hostname", "work.example.com",
            "--config-file", "10-work-servers",
        )
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=ssh_dir)
        host = mgr.get_host("work-server")
        assert host is not None
        assert host.source_file is not None
        assert host.source_file.name == "10-work-servers"


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------

class TestEditCommand:
    def test_edit_hostname(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "web-server", "--hostname", "10.0.0.99")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("web-server").hostname == "10.0.0.99"

    def test_edit_user(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "web-server", "--user", "root")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("web-server").user == "root"

    def test_edit_port(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "web-server", "--port", "2222")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("web-server").port == 2222

    def test_edit_identity_file(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "web-server", "--identity-file", "~/.ssh/custom")
        assert result.exit_code == 0

    def test_edit_nonexistent_host(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "ghost", "--hostname", "10.99.99.99")
        assert result.exit_code == 1

    def test_edit_no_changes_is_noop(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "edit", "web-server")
        assert result.exit_code == 0
        assert "No changes" in result.output


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestRemoveCommand:
    def test_remove_with_yes_flag(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "remove", "web-server", "--yes")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("web-server") is None

    def test_remove_with_confirmation(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "remove", "db-server", input="y\n")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("db-server") is None

    def test_remove_with_denied_confirmation(self, runner, populated_ssh_dir):
        result = runner.invoke(
            cli, ["--ssh-dir", str(populated_ssh_dir), "remove", "web-server"],
            input="n\n",
            catch_exceptions=False,
        )
        # Aborted — exit_code 1 is expected from click.Abort
        assert result.exit_code != 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert mgr.get_host("web-server") is not None

    def test_remove_nonexistent_host(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "remove", "ghost", "--yes")
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# connect / sftp (error paths only — os.execvp has pragma no cover)
# ---------------------------------------------------------------------------

class TestConnectCommand:
    def test_connect_nonexistent_host_fails(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "connect", "ghost")
        assert result.exit_code == 1


class TestSftpCommand:
    def test_sftp_nonexistent_host_fails(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "sftp", "ghost")
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearchCommand:
    def test_search_finds_match(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "search", "web")
        assert result.exit_code == 0
        assert "web-server" in result.output

    def test_search_no_match(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "search", "zzznomatch")
        assert result.exit_code == 0
        assert "No hosts found" in result.output


# ---------------------------------------------------------------------------
# config subgroup
# ---------------------------------------------------------------------------

class TestConfigList:
    def test_config_list_empty(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "config", "list")
        assert result.exit_code == 0
        assert "No config files found" in result.output

    def test_config_list_shows_files(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "config", "list")
        assert result.exit_code == 0
        assert "test-hosts" in result.output


class TestConfigCreate:
    def test_config_create_success(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "config", "create", "my-hosts")
        assert result.exit_code == 0
        assert "my-hosts" in result.output
        mgr = SSHManager(ssh_dir=ssh_dir)
        assert any(f.name == "my-hosts" for f in mgr.list_config_files())

    def test_config_create_duplicate_fails(self, runner, populated_ssh_dir):
        # test-hosts already exists
        result = invoke(runner, populated_ssh_dir, "config", "create", "test-hosts")
        assert result.exit_code == 1


class TestConfigDelete:
    def test_config_delete_with_yes(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "config", "delete", "test-hosts", "--yes")
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=populated_ssh_dir)
        assert not any(f.name == "test-hosts" for f in mgr.list_config_files())

    def test_config_delete_nonexistent_fails(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "config", "delete", "nonexistent", "--yes")
        assert result.exit_code == 1

    def test_config_delete_with_confirmation(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "config", "delete", "test-hosts", input="y\n")
        assert result.exit_code == 0


class TestConfigShow:
    def test_config_show_existing(self, runner, populated_ssh_dir):
        result = invoke(runner, populated_ssh_dir, "config", "show", "test-hosts")
        assert result.exit_code == 0
        assert "web-server" in result.output

    def test_config_show_nonexistent_fails(self, runner, ssh_dir):
        result = invoke(runner, ssh_dir, "config", "show", "ghost")
        assert result.exit_code == 1


class TestConfigInit:
    def test_config_init(self, runner, tmp_path):
        bare_ssh = tmp_path / ".ssh"
        result = invoke(runner, bare_ssh, "config", "init")
        assert result.exit_code == 0
        assert "ready" in result.output
        assert (bare_ssh / "config.d").is_dir()


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

class TestMigrateCommand:
    def test_migrate_dry_run(self, runner, ssh_dir, legacy_config_dir):
        result = invoke(
            runner, ssh_dir,
            "migrate",
            "--source", str(legacy_config_dir),
            "--dry-run",
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        # Nothing should be written
        mgr = SSHManager(ssh_dir=ssh_dir)
        assert mgr.list_hosts() == []

    def test_migrate_live(self, runner, ssh_dir, legacy_config_dir):
        result = invoke(
            runner, ssh_dir,
            "migrate",
            "--source", str(legacy_config_dir),
            "--config-file", "migrated",
        )
        assert result.exit_code == 0
        mgr = SSHManager(ssh_dir=ssh_dir)
        hosts = {h.name for h in mgr.list_hosts()}
        assert len(hosts) >= 2  # vm1 and vm3 at minimum (vm2 has same IP)

    def test_migrate_empty_source(self, runner, ssh_dir, tmp_path):
        empty_dir = tmp_path / "empty_legacy"
        empty_dir.mkdir()
        result = invoke(
            runner, ssh_dir,
            "migrate",
            "--source", str(empty_dir),
        )
        assert result.exit_code == 0
        assert "Nothing" in result.output

    def test_migrate_nonexistent_source(self, runner, ssh_dir, tmp_path):
        result = invoke(
            runner, ssh_dir,
            "migrate",
            "--source", str(tmp_path / "does_not_exist"),
        )
        assert result.exit_code == 0
        assert "Nothing" in result.output

    def test_migrate_warns_about_password(self, runner, ssh_dir, legacy_config_dir):
        result = invoke(
            runner, ssh_dir,
            "migrate",
            "--source", str(legacy_config_dir),
            "--config-file", "migrated2",
        )
        assert result.exit_code == 0
        # Password warning should appear in output
        assert "password" in result.output.lower()

    def test_migrate_force_overwrites(self, runner, ssh_dir, legacy_config_dir):
        # First migration
        invoke(runner, ssh_dir, "migrate", "--source", str(legacy_config_dir), "--config-file", "mig")
        # Second migration fails without --force
        result2 = invoke(runner, ssh_dir, "migrate", "--source", str(legacy_config_dir), "--config-file", "mig")
        assert result2.exit_code == 1
        # With --force it succeeds
        result3 = invoke(runner, ssh_dir, "migrate", "--source", str(legacy_config_dir), "--config-file", "mig", "--force")
        assert result3.exit_code == 0

#     assert 'Group created' in result.output  # Replace with expected success message
#
# # Test for add-server command
# def test_add_server(runner):
#     group_path = 'test_group'
#     alias = 'test_alias'
#     host = 'test_host'
#     result = runner.invoke(cli, ['add-server', group_path, alias, host, '--port', '22'])
#     assert result.exit_code == 0
#     assert 'Server added' in result.output  # Replace with expected success message

