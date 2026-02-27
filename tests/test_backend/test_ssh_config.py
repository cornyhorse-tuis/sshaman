"""Tests for backend/ssh_config.py — SSHConfigManager."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from backend.host_entry import HostEntry
from backend.ssh_config import (
    SSHConfigError,
    SSHConfigManager,
    _remove_block_from_text,
    _split_into_blocks,
    _validate_config_file_name,
    _INCLUDE_DIRECTIVE,
)


# ---------------------------------------------------------------------------
# _validate_config_file_name
# ---------------------------------------------------------------------------

class TestValidateConfigFileName:
    def test_valid_name_returns_path(self, tmp_path):
        config_d = tmp_path / "config.d"
        config_d.mkdir()
        path = _validate_config_file_name(config_d, "10-work")
        assert path == config_d / "10-work"

    def test_empty_name_raises(self, tmp_path):
        with pytest.raises(SSHConfigError, match="empty"):
            _validate_config_file_name(tmp_path, "")

    def test_slash_in_name_raises(self, tmp_path):
        with pytest.raises(SSHConfigError, match="path separators"):
            _validate_config_file_name(tmp_path, "sub/file")

    def test_null_byte_raises(self, tmp_path):
        with pytest.raises(SSHConfigError, match="null bytes"):
            _validate_config_file_name(tmp_path, "file\x00bad")

    def test_dotdot_raises(self, tmp_path):
        with pytest.raises(SSHConfigError):
            _validate_config_file_name(tmp_path, "..")

    def test_dot_raises(self, tmp_path):
        with pytest.raises(SSHConfigError):
            _validate_config_file_name(tmp_path, ".")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entry(name: str = "srv", hostname: str = "10.0.0.1", **kw) -> HostEntry:
    return HostEntry(name=name, hostname=hostname, **kw)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def permissions(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---------------------------------------------------------------------------
# ensure_config_d_setup
# ---------------------------------------------------------------------------

class TestEnsureConfigDSetup:
    def test_backup_created_when_config_has_content(self, tmp_path):
        """A timestamped backup of ~/.ssh/config is made before prepending Include."""
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        cfg = ssh / "config"
        original_content = "Host old-entry\n    HostName 1.2.3.4\n"
        cfg.write_text(original_content, encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        backups = list(ssh.glob("config.bak.*"))
        assert len(backups) == 1, "Expected exactly one backup file"
        assert backups[0].read_text(encoding="utf-8") == original_content

    def test_no_backup_when_config_is_empty(self, tmp_path):
        """No backup is created when config is empty (nothing to preserve)."""
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        (ssh / "config").write_text("", encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        backups = list(ssh.glob("config.bak.*"))
        assert backups == [], "No backup expected for an empty config"

    def test_creates_config_d_when_missing(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        assert (ssh / "config.d").is_dir()

    def test_creates_config_when_missing(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        assert (ssh / "config").exists()

    def test_adds_include_to_existing_empty_config(self, ssh_dir):
        # Re-write config without the Include
        cfg = ssh_dir / "config"
        cfg.write_text("", encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        mgr.ensure_config_d_setup()
        assert _INCLUDE_DIRECTIVE in read(cfg)

    def test_does_not_duplicate_include(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        mgr.ensure_config_d_setup()
        mgr.ensure_config_d_setup()  # second call
        content = read(ssh_dir / "config")
        assert content.count(_INCLUDE_DIRECTIVE) == 1

    def test_include_prepended(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        cfg = ssh / "config"
        cfg.write_text("Host old-entry\n    HostName 1.2.3.4\n", encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        content = read(cfg)
        assert content.startswith(_INCLUDE_DIRECTIVE)

    def test_creates_ssh_dir_when_missing(self, tmp_path):
        ssh = tmp_path / "new_ssh"
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        assert ssh.is_dir()

    def test_config_file_permissions(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        assert permissions(ssh / "config") == 0o600

    def test_config_d_permissions(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        mgr.ensure_config_d_setup()
        assert permissions(ssh / "config.d") == 0o700

    def test_idempotent_on_already_set_up_dir(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        # Should not raise even though everything is already configured
        mgr.ensure_config_d_setup()
        mgr.ensure_config_d_setup()


# ---------------------------------------------------------------------------
# list_config_files
# ---------------------------------------------------------------------------

class TestListConfigFiles:
    def test_returns_sorted_list(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        files = mgr.list_config_files()
        names = [f.name for f in files]
        assert names == sorted(names)
        assert "extra-hosts" in names
        assert "test-hosts" in names

    def test_empty_when_config_d_missing(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        assert mgr.list_config_files() == []

    def test_directories_excluded(self, sample_ssh_dir):
        (sample_ssh_dir / "config.d" / "subdir").mkdir()
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        files = mgr.list_config_files()
        assert all(f.is_file() for f in files)


# ---------------------------------------------------------------------------
# create_config_file
# ---------------------------------------------------------------------------

class TestCreateConfigFile:
    def test_creates_file(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        path = mgr.create_config_file("new-hosts")
        assert path.exists()
        assert path.name == "new-hosts"

    def test_permissions_are_600(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        path = mgr.create_config_file("new-hosts")
        assert permissions(path) == 0o600

    def test_raises_if_already_exists(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        with pytest.raises(SSHConfigError, match="already exists"):
            mgr.create_config_file("test-hosts")

    def test_raises_on_path_separator_in_name(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError, match="path separators"):
            mgr.create_config_file("sub/file")

    def test_raises_on_dotdot_traversal(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError):
            mgr.create_config_file("..")

    def test_raises_on_empty_name(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError, match="empty"):
            mgr.create_config_file("")

    def test_file_is_empty(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        path = mgr.create_config_file("empty")
        assert path.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# delete_config_file
# ---------------------------------------------------------------------------

class TestDeleteConfigFile:
    def test_deletes_existing_file(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        mgr.delete_config_file("extra-hosts")
        assert not (sample_ssh_dir / "config.d" / "extra-hosts").exists()

    def test_raises_when_file_missing(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError, match="does not exist"):
            mgr.delete_config_file("nonexistent")

    def test_raises_on_path_separator_in_name(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        with pytest.raises(SSHConfigError, match="path separators"):
            mgr.delete_config_file("../config")

    def test_raises_on_dotdot_traversal(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        with pytest.raises(SSHConfigError):
            mgr.delete_config_file("..")


# ---------------------------------------------------------------------------
# read_hosts_from_file
# ---------------------------------------------------------------------------

class TestReadHostsFromFile:
    def test_reads_two_hosts(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        assert len(hosts) == 2
        names = {h.name for h in hosts}
        assert names == {"web-server", "db-server"}

    def test_source_file_set_on_entries(self, sample_ssh_dir):
        path = sample_ssh_dir / "config.d" / "test-hosts"
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        hosts = mgr.read_hosts_from_file(path)
        assert all(h.source_file == path for h in hosts)

    def test_raises_when_file_missing(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError, match="not found"):
            mgr.read_hosts_from_file(ssh_dir / "config.d" / "ghost")

    def test_empty_file_returns_empty_list(self, ssh_dir):
        f = ssh_dir / "config.d" / "empty"
        f.touch()
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        assert mgr.read_hosts_from_file(f) == []

    def test_comments_only_file_returns_empty_list(self, ssh_dir):
        f = ssh_dir / "config.d" / "comments"
        f.write_text("# Just a comment\n# Another comment\n", encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        assert mgr.read_hosts_from_file(f) == []


# ---------------------------------------------------------------------------
# read_all_hosts
# ---------------------------------------------------------------------------

class TestReadAllHosts:
    def test_reads_all_hosts_across_files(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        hosts = mgr.read_all_hosts()
        names = {h.name for h in hosts}
        assert names == {"web-server", "db-server", "jump-box"}

    def test_empty_when_no_config_d(self, tmp_path):
        ssh = tmp_path / ".ssh"
        ssh.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh)
        assert mgr.read_all_hosts() == []


# ---------------------------------------------------------------------------
# write_host
# ---------------------------------------------------------------------------

class TestWriteHost:
    def test_appends_host_to_existing_file(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        entry = make_entry("new-host", "10.99.0.1")
        mgr.write_host(entry, "test-hosts")
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        assert any(h.name == "new-host" for h in hosts)

    def test_creates_new_file_if_missing(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        entry = make_entry("srv", "10.0.0.1")
        mgr.write_host(entry, "brand-new")
        assert (ssh_dir / "config.d" / "brand-new").exists()

    def test_permissions_on_new_file(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        mgr.write_host(make_entry(), "new-file")
        path = ssh_dir / "config.d" / "new-file"
        assert permissions(path) == 0o600

    def test_raises_on_path_separator_in_config_file_name(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError, match="path separators"):
            mgr.write_host(make_entry(), "../injected")

    def test_raises_on_dotdot_config_file_name(self, ssh_dir):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        with pytest.raises(SSHConfigError):
            mgr.write_host(make_entry(), "..")


# ---------------------------------------------------------------------------
# remove_host
# ---------------------------------------------------------------------------

class TestRemoveHost:
    def test_removes_host_from_file(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        mgr.remove_host("web-server")
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        assert not any(h.name == "web-server" for h in hosts)

    def test_preserves_other_hosts(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        mgr.remove_host("web-server")
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        assert any(h.name == "db-server" for h in hosts)

    def test_raises_when_host_not_found(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        with pytest.raises(SSHConfigError, match="Host not found"):
            mgr.remove_host("ghost-server")

    def test_removes_only_host_from_file(self, ssh_dir):
        f = ssh_dir / "config.d" / "single"
        f.write_text("Host only\n    HostName 1.2.3.4\n\n", encoding="utf-8")
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        mgr.remove_host("only")
        hosts = mgr.read_hosts_from_file(f)
        assert hosts == []


# ---------------------------------------------------------------------------
# update_host
# ---------------------------------------------------------------------------

class TestUpdateHost:
    def test_updates_hostname(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        updated = HostEntry(name="web-server", hostname="10.99.99.99", user="admin")
        mgr.update_host("web-server", updated)
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        web = next(h for h in hosts if h.name == "web-server")
        assert web.hostname == "10.99.99.99"

    def test_other_hosts_preserved(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        updated = HostEntry(name="web-server", hostname="10.99.99.99")
        mgr.update_host("web-server", updated)
        hosts = mgr.read_hosts_from_file(sample_ssh_dir / "config.d" / "test-hosts")
        assert any(h.name == "db-server" for h in hosts)

    def test_raises_when_host_not_found(self, sample_ssh_dir):
        mgr = SSHConfigManager(ssh_dir=sample_ssh_dir)
        with pytest.raises(SSHConfigError, match="Host not found"):
            mgr.update_host("ghost", HostEntry(name="ghost", hostname="h"))


# ---------------------------------------------------------------------------
# _split_into_blocks (parsing helper)
# ---------------------------------------------------------------------------

class TestSplitIntoBlocks:
    def test_skips_wildcard_host(self, ssh_dir):
        text = "Host *\n    ServerAliveInterval 60\n\nHost real\n    HostName 1.1.1.1\n"
        blocks = _split_into_blocks(text, ssh_dir)
        assert len(blocks) == 1
        assert blocks[0].name == "real"

    def test_skips_match_block(self, ssh_dir):
        text = "Match host *.example.com\n    User auto\n\nHost real\n    HostName 1.1.1.1\n"
        blocks = _split_into_blocks(text, ssh_dir)
        assert len(blocks) == 1
        assert blocks[0].name == "real"

    def test_malformed_block_skipped_silently(self, ssh_dir):
        text = "NotAHost\n    something\n\nHost valid\n    HostName h\n"
        blocks = _split_into_blocks(text, ssh_dir)
        assert len(blocks) == 1

    def test_empty_text_returns_empty_list(self, ssh_dir):
        assert _split_into_blocks("", ssh_dir) == []

    def test_comments_only_returns_empty_list(self, ssh_dir):
        assert _split_into_blocks("# just comments\n", ssh_dir) == []

    def test_comment_before_host_attached_as_comment(self, ssh_dir):
        text = "# My host\nHost s\n    HostName h\n"
        blocks = _split_into_blocks(text, ssh_dir)
        assert blocks[0].comment == "# My host"

    def test_multiple_blocks(self, ssh_dir):
        text = (
            "Host a\n    HostName 1.1.1.1\n\n"
            "Host b\n    HostName 2.2.2.2\n\n"
        )
        blocks = _split_into_blocks(text, ssh_dir)
        assert len(blocks) == 2


# ---------------------------------------------------------------------------
# _remove_block_from_text (internal helper)
# ---------------------------------------------------------------------------

class TestRemoveBlockFromText:
    def test_removes_target_block(self):
        text = "Host a\n    HostName 1.1.1.1\n\nHost b\n    HostName 2.2.2.2\n"
        result = _remove_block_from_text(text, "a")
        assert "Host a" not in result
        assert "Host b" in result

    def test_removes_with_comment(self):
        text = "# Comment for a\nHost a\n    HostName 1.1.1.1\n\nHost b\n    HostName 2.2.2.2\n"
        result = _remove_block_from_text(text, "a")
        assert "Comment for a" not in result
        assert "Host b" in result

    def test_noop_when_host_not_in_text(self):
        text = "Host a\n    HostName h\n"
        result = _remove_block_from_text(text, "ghost")
        assert result == text

    def test_removes_only_block(self):
        text = "Host only\n    HostName h\n"
        result = _remove_block_from_text(text, "only")
        assert "Host only" not in result


# ---------------------------------------------------------------------------
# _safe_write — exception cleanup
# ---------------------------------------------------------------------------

class TestSafeWriteExceptionHandling:
    """Test that _safe_write cleans up temp files on failure."""

    def test_safe_write_removes_temp_on_failure(self, config_manager: SSHConfigManager):
        """When the rename step fails, the temp file should be cleaned up."""
        entry = HostEntry(name="boom", hostname="1.2.3.4")

        original_replace = Path.replace

        def failing_replace(self, target):
            raise OSError("simulated disk error")

        # Monkeypatch Path.replace to fail
        Path.replace = failing_replace  # type: ignore[assignment]
        try:
            with pytest.raises(OSError, match="simulated disk error"):
                config_manager.write_host(entry, "test-file")
        finally:
            Path.replace = original_replace  # type: ignore[assignment]

        # No stale .tmp files should remain in config.d
        tmp_files = list(config_manager.config_d.glob("*.tmp"))
        assert tmp_files == []


# ---------------------------------------------------------------------------
# _split_into_blocks — malformed blocks
# ---------------------------------------------------------------------------

class TestSplitIntoBlocksMalformed:
    """Test that _split_into_blocks gracefully skips malformed Host blocks."""

    def test_malformed_host_block_skipped(self, tmp_path: Path):
        """A Host block with no alias should be silently skipped."""
        config_file = tmp_path / "bad-config"
        # "Host" with no alias triggers ValueError in from_ssh_config_block
        config_file.write_text(
            "Host good-host\n"
            "    HostName 1.2.3.4\n"
            "    User admin\n"
            "\n"
            "Host\n"
            "    HostName 9.9.9.9\n"
            "\n"
            "Host also-good\n"
            "    HostName 5.6.7.8\n"
            "\n",
            encoding="utf-8",
        )
        entries = _split_into_blocks(config_file.read_text(), source_file=config_file)
        names = [e.name for e in entries]
        assert "good-host" in names
        assert "also-good" in names
        assert len(entries) == 2
