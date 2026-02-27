"""Tests for backend/manager.py — SSHManager high-level operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.host_entry import HostEntry
from backend.manager import (
    DuplicateHostError,
    HostNotFoundError,
    SSHManager,
)
from backend.ssh_config import SSHConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def entry(name: str, hostname: str = "10.0.0.1", **kw) -> HostEntry:
    return HostEntry(name=name, hostname=hostname, **kw)


# ---------------------------------------------------------------------------
# list_hosts
# ---------------------------------------------------------------------------


class TestListHosts:
    def test_returns_all_hosts(self, manager: SSHManager):
        hosts = manager.list_hosts()
        names = {h.name for h in hosts}
        assert names == {"web-server", "db-server", "jump-box"}

    def test_returns_empty_when_no_hosts(self, empty_manager: SSHManager):
        assert empty_manager.list_hosts() == []

    def test_filter_by_alias(self, manager: SSHManager):
        results = manager.list_hosts(filter="web")
        assert len(results) == 1
        assert results[0].name == "web-server"

    def test_filter_by_hostname(self, manager: SSHManager):
        results = manager.list_hosts(filter="192.168.1.100")
        assert len(results) == 1
        assert results[0].name == "web-server"

    def test_filter_by_user(self, manager: SSHManager):
        results = manager.list_hosts(filter="postgres")
        assert len(results) == 1
        assert results[0].name == "db-server"

    def test_filter_case_insensitive(self, manager: SSHManager):
        results = manager.list_hosts(filter="WEB")
        assert len(results) == 1

    def test_filter_no_match_returns_empty(self, manager: SSHManager):
        assert manager.list_hosts(filter="zzznomatch") == []

    def test_filter_none_returns_all(self, manager: SSHManager):
        assert len(manager.list_hosts(filter=None)) == 3

    def test_filter_partial_hostname(self, manager: SSHManager):
        results = manager.list_hosts(filter="192.168")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# get_host
# ---------------------------------------------------------------------------


class TestGetHost:
    def test_returns_host_by_name(self, manager: SSHManager):
        host = manager.get_host("web-server")
        assert host is not None
        assert host.name == "web-server"
        assert host.hostname == "192.168.1.100"

    def test_returns_none_for_missing_host(self, manager: SSHManager):
        assert manager.get_host("does-not-exist") is None

    def test_returns_correct_fields(self, manager: SSHManager):
        host = manager.get_host("db-server")
        assert host.port == 5432
        assert host.user == "postgres"


# ---------------------------------------------------------------------------
# add_host
# ---------------------------------------------------------------------------


class TestAddHost:
    def test_adds_host_to_default_file(self, empty_manager: SSHManager, ssh_dir: Path):
        new = entry("newbie", "10.99.0.1")
        empty_manager.add_host(new)
        assert empty_manager.get_host("newbie") is not None

    def test_adds_host_to_specified_file(
        self, empty_manager: SSHManager, ssh_dir: Path
    ):
        new = entry("srv", "10.0.0.5")
        empty_manager.add_host(new, config_file="my-hosts")
        path = ssh_dir / "config.d" / "my-hosts"
        assert path.exists()
        assert empty_manager.get_host("srv") is not None

    def test_raises_on_duplicate_alias(self, manager: SSHManager):
        duplicate = entry("web-server", "1.2.3.4")
        with pytest.raises(DuplicateHostError, match="already exists"):
            manager.add_host(duplicate)

    def test_creates_config_d_if_missing(self, tmp_path: Path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHManager(ssh_dir=ssh)
        mgr.add_host(entry("fresh", "1.2.3.4"))
        assert mgr.get_host("fresh") is not None


# ---------------------------------------------------------------------------
# edit_host
# ---------------------------------------------------------------------------


class TestEditHost:
    def test_updates_hostname(self, manager: SSHManager):
        updated = manager.edit_host("web-server", hostname="10.99.0.1")
        assert updated.hostname == "10.99.0.1"
        # Verify persisted
        assert manager.get_host("web-server").hostname == "10.99.0.1"

    def test_updates_user(self, manager: SSHManager):
        updated = manager.edit_host("web-server", user="newuser")
        assert updated.user == "newuser"

    def test_updates_port(self, manager: SSHManager):
        updated = manager.edit_host("db-server", port=3306)
        assert updated.port == 3306

    def test_raises_when_host_not_found(self, manager: SSHManager):
        with pytest.raises(HostNotFoundError, match="not found"):
            manager.edit_host("ghost", hostname="1.2.3.4")

    def test_other_hosts_unaffected(self, manager: SSHManager):
        manager.edit_host("web-server", hostname="9.9.9.9")
        db = manager.get_host("db-server")
        assert db.hostname == "192.168.1.101"


# ---------------------------------------------------------------------------
# remove_host
# ---------------------------------------------------------------------------


class TestRemoveHost:
    def test_removes_host(self, manager: SSHManager):
        manager.remove_host("jump-box")
        assert manager.get_host("jump-box") is None

    def test_raises_when_host_not_found(self, manager: SSHManager):
        with pytest.raises(HostNotFoundError, match="not found"):
            manager.remove_host("ghost")

    def test_other_hosts_unaffected(self, manager: SSHManager):
        manager.remove_host("jump-box")
        assert manager.get_host("web-server") is not None
        assert manager.get_host("db-server") is not None


# ---------------------------------------------------------------------------
# connect_command / sftp_command
# ---------------------------------------------------------------------------


class TestConnectCommand:
    def test_returns_ssh_alias_list(self, manager: SSHManager):
        cmd = manager.connect_command("web-server")
        assert cmd == ["ssh", "--", "web-server"]

    def test_raises_when_host_not_found(self, manager: SSHManager):
        with pytest.raises(HostNotFoundError):
            manager.connect_command("ghost")


class TestSftpCommand:
    def test_returns_sftp_alias_list(self, manager: SSHManager):
        cmd = manager.sftp_command("web-server")
        assert cmd == ["sftp", "--", "web-server"]

    def test_raises_when_host_not_found(self, manager: SSHManager):
        with pytest.raises(HostNotFoundError):
            manager.sftp_command("ghost")


# ---------------------------------------------------------------------------
# Config file management
# ---------------------------------------------------------------------------


class TestListConfigFiles:
    def test_returns_correct_files(self, manager: SSHManager, sample_ssh_dir: Path):
        files = manager.list_config_files()
        names = [f.name for f in files]
        assert "test-hosts" in names
        assert "extra-hosts" in names

    def test_returns_empty_for_empty_dir(self, empty_manager: SSHManager):
        assert empty_manager.list_config_files() == []


class TestCreateConfigFile:
    def test_creates_file(self, empty_manager: SSHManager, ssh_dir: Path):
        path = empty_manager.create_config_file("10-work")
        assert path.exists()

    def test_raises_on_duplicate(self, manager: SSHManager):
        with pytest.raises(SSHConfigError):
            manager.create_config_file("test-hosts")


class TestDeleteConfigFile:
    def test_deletes_file(self, manager: SSHManager, sample_ssh_dir: Path):
        manager.delete_config_file("extra-hosts")
        assert not (sample_ssh_dir / "config.d" / "extra-hosts").exists()

    def test_raises_when_missing(self, manager: SSHManager):
        with pytest.raises(SSHConfigError):
            manager.delete_config_file("nonexistent")


# ---------------------------------------------------------------------------
# ensure_setup
# ---------------------------------------------------------------------------


class TestEnsureSetup:
    def test_idempotent(self, manager: SSHManager):
        manager.ensure_setup()
        manager.ensure_setup()  # should not raise
