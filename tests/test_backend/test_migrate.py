"""Tests for backend/migrate.py — legacy JSON to SSH config migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.migrate import (
    convert_json_to_host_entry,
    discover_json_configs,
    migrate,
)
from backend.ssh_config import SSHConfigError, SSHConfigManager


# ---------------------------------------------------------------------------
# discover_json_configs
# ---------------------------------------------------------------------------


class TestDiscoverJsonConfigs:
    def test_finds_all_json_files(self, legacy_config_dir: Path):
        results = discover_json_configs(legacy_config_dir)
        assert len(results) == 3

    def test_returns_path_and_dict(self, legacy_config_dir: Path):
        results = discover_json_configs(legacy_config_dir)
        for path, data in results:
            assert isinstance(path, Path)
            assert isinstance(data, dict)

    def test_empty_directory_returns_empty(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert discover_json_configs(empty) == []

    def test_non_json_files_ignored(self, tmp_path: Path):
        (tmp_path / "server.txt").write_text("not json")
        (tmp_path / "README.md").write_text("# readme")
        assert discover_json_configs(tmp_path) == []

    def test_malformed_json_ignored(self, tmp_path: Path):
        (tmp_path / "bad.json").write_text("{not valid json}")
        assert discover_json_configs(tmp_path) == []

    def test_non_dict_json_ignored(self, tmp_path: Path):
        (tmp_path / "list.json").write_text("[1, 2, 3]")
        assert discover_json_configs(tmp_path) == []

    def test_finds_nested_json(self, legacy_config_dir: Path):
        results = discover_json_configs(legacy_config_dir)
        paths = [r[0] for r in results]
        # vm1 and vm2 are in group1/, vm3 in group2/
        assert any("group1" in str(p) for p in paths)
        assert any("group2" in str(p) for p in paths)


# ---------------------------------------------------------------------------
# convert_json_to_host_entry
# ---------------------------------------------------------------------------


class TestConvertJsonToHostEntry:
    def _base_data(self, **overrides) -> dict:
        d = {
            "alias": "vm1",
            "host": "192.168.1.100",
            "port": 22,
            "user": "root",
            "identity_file": "~/.ssh/id_rsa",
            "forward_ports": [],
            "start_commands": [],
            "server_group_path": "/tmp/group1",
        }
        d.update(overrides)
        return d

    def test_basic_conversion(self, tmp_path: Path):
        data = self._base_data()
        entry, warns = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        assert entry.name == "vm1"
        assert entry.hostname == "192.168.1.100"
        assert entry.port == 22
        assert entry.user == "root"
        assert warns == []

    def test_warns_on_password(self, tmp_path: Path):
        data = self._base_data(password="s3cr3t")
        _, warns = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        assert any("password" in w.lower() for w in warns)

    def test_warns_on_start_commands(self, tmp_path: Path):
        data = self._base_data(start_commands=["echo hi"])
        _, warns = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        assert any("start_commands" in w.lower() for w in warns)

    def test_forward_ports_converted(self, tmp_path: Path):
        data = self._base_data(forward_ports=["8080:localhost:80", ""])
        entry, _ = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        # Empty strings should be filtered
        assert entry.local_forwards == ["8080:localhost:80"]

    def test_identity_file_set(self, tmp_path: Path):
        data = self._base_data(identity_file="~/.ssh/id_ed25519")
        entry, _ = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        assert str(entry.identity_file) == "~/.ssh/id_ed25519"

    def test_identity_file_null(self, tmp_path: Path):
        data = self._base_data(identity_file=None)
        entry, _ = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        assert entry.identity_file is None

    def test_comment_includes_group_path(self, tmp_path: Path):
        (tmp_path / "group1").mkdir()
        json_path = tmp_path / "group1" / "vm1.json"
        data = self._base_data()
        entry, _ = convert_json_to_host_entry(json_path, data, tmp_path)
        assert "group1" in (entry.comment or "")

    def test_comment_fallback_when_at_root(self, tmp_path: Path):
        json_path = tmp_path / "vm1.json"
        data = self._base_data()
        entry, _ = convert_json_to_host_entry(json_path, data, tmp_path)
        assert entry.comment is not None

    def test_comment_fallback_when_path_not_relative(self, tmp_path: Path):
        """When json_path is not under source_root, use fallback comment."""
        unrelated_dir = tmp_path / "unrelated"
        unrelated_dir.mkdir()
        json_path = unrelated_dir / "vm1.json"
        source_root = tmp_path / "completely" / "different"
        source_root.mkdir(parents=True)
        data = self._base_data()
        entry, _ = convert_json_to_host_entry(json_path, data, source_root)
        assert entry.comment is not None
        assert "Migrated by SSHaMan" in entry.comment

    def test_raises_on_missing_alias(self, tmp_path: Path):
        data = {"host": "1.2.3.4", "port": 22}
        with pytest.raises(KeyError):
            convert_json_to_host_entry(tmp_path / "f.json", data, tmp_path)

    def test_raises_on_missing_host(self, tmp_path: Path):
        data = {"alias": "vm", "port": 22}
        with pytest.raises(KeyError):
            convert_json_to_host_entry(tmp_path / "f.json", data, tmp_path)

    def test_server_group_path_dropped(self, tmp_path: Path):
        data = self._base_data()
        entry, _ = convert_json_to_host_entry(tmp_path / "vm1.json", data, tmp_path)
        # server_group_path is not a field in HostEntry
        assert not hasattr(entry, "server_group_path")


# ---------------------------------------------------------------------------
# migrate — dry run
# ---------------------------------------------------------------------------


class TestMigrateDryRun:
    def test_dry_run_does_not_write(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=legacy_config_dir, config_manager=mgr, dry_run=True)
        # Nothing should be written
        assert not (ssh_dir / "config.d" / "sshaman-migrated").exists()
        # But results should be populated
        assert len(result.migrated) == 3
        assert result.dry_run is True

    def test_dry_run_reports_warnings(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=legacy_config_dir, config_manager=mgr, dry_run=True)
        # vm2 has a password — should produce a warning
        assert "vm2" in result.warnings

    def test_dry_run_no_errors_on_valid_data(
        self, legacy_config_dir: Path, ssh_dir: Path
    ):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=legacy_config_dir, config_manager=mgr, dry_run=True)
        assert result.errors == {}


# ---------------------------------------------------------------------------
# migrate — live run
# ---------------------------------------------------------------------------


class TestMigrateLive:
    def test_writes_hosts_to_config_file(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        migrate(source=legacy_config_dir, config_manager=mgr)
        assert (ssh_dir / "config.d" / "sshaman-migrated").exists()
        hosts = mgr.read_hosts_from_file(ssh_dir / "config.d" / "sshaman-migrated")
        names = {h.name for h in hosts}
        assert "vm1" in names
        assert "vm2" in names
        assert "vm3" in names

    def test_raises_when_target_exists_without_force(
        self, legacy_config_dir: Path, ssh_dir: Path
    ):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        migrate(source=legacy_config_dir, config_manager=mgr)  # first run
        with pytest.raises(SSHConfigError, match="already exists"):
            migrate(source=legacy_config_dir, config_manager=mgr)  # second run

    def test_force_overwrites_existing(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        migrate(source=legacy_config_dir, config_manager=mgr)
        # Second run with force — should not raise
        result = migrate(source=legacy_config_dir, config_manager=mgr, force=True)
        assert len(result.migrated) == 3

    def test_custom_config_file_name(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        migrate(
            source=legacy_config_dir, config_manager=mgr, config_file="my-migration"
        )
        assert (ssh_dir / "config.d" / "my-migration").exists()

    def test_empty_source_returns_empty_result(self, tmp_path: Path, ssh_dir: Path):
        empty_src = tmp_path / "empty"
        empty_src.mkdir()
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=empty_src, config_manager=mgr)
        assert result.migrated == []

    def test_nonexistent_source_returns_empty_result(
        self, tmp_path: Path, ssh_dir: Path
    ):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=tmp_path / "ghost", config_manager=mgr)
        assert result.migrated == []

    def test_duplicate_aliases_are_renamed(self, tmp_path: Path, ssh_dir: Path):
        # Create two JSON files with the same alias
        src = tmp_path / "legacy"
        src.mkdir()
        for i in range(2):
            (src / f"srv{i}.json").write_text(
                json.dumps(
                    {
                        "alias": "same-name",
                        "host": f"10.0.0.{i + 1}",
                        "port": 22,
                        "user": "u",
                        "identity_file": None,
                        "forward_ports": [],
                        "start_commands": [],
                    }
                )
            )
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=src, config_manager=mgr)
        names = [e.name for e in result.migrated]
        # Both entries should have distinct names
        assert len(set(names)) == 2

    def test_errors_reported_for_invalid_json(self, tmp_path: Path, ssh_dir: Path):
        src = tmp_path / "legacy"
        src.mkdir()
        # Valid entry
        (src / "good.json").write_text(
            json.dumps(
                {
                    "alias": "good",
                    "host": "1.2.3.4",
                    "port": 22,
                    "user": "u",
                    "identity_file": None,
                    "forward_ports": [],
                    "start_commands": [],
                }
            )
        )
        # Entry missing "alias"
        (src / "bad.json").write_text(json.dumps({"host": "1.2.3.4"}))
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=src, config_manager=mgr)
        assert len(result.migrated) == 1
        assert len(result.errors) == 1

    def test_password_not_in_output(self, legacy_config_dir: Path, ssh_dir: Path):
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        migrate(source=legacy_config_dir, config_manager=mgr)
        content = (ssh_dir / "config.d" / "sshaman-migrated").read_text()
        assert "s3cr3t" not in content
        assert "password" not in content.lower()

    def test_source_cleanup_reminder_set_after_real_migration(
        self, legacy_config_dir: Path, ssh_dir: Path
    ):
        """After a real migration the result contains a reminder to clean up legacy files."""
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=legacy_config_dir, config_manager=mgr)
        assert result.source_cleanup_reminder != ""
        assert str(legacy_config_dir) in result.source_cleanup_reminder

    def test_no_cleanup_reminder_on_dry_run(
        self, legacy_config_dir: Path, ssh_dir: Path
    ):
        """Dry-run migrations must not set the cleanup reminder (nothing was written)."""
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        result = migrate(source=legacy_config_dir, config_manager=mgr, dry_run=True)
        assert result.source_cleanup_reminder == ""

    def test_force_overwrites_existing_target(
        self, legacy_config_dir: Path, ssh_dir: Path
    ):
        """force=True allows re-running migration to an existing target file."""
        mgr = SSHConfigManager(ssh_dir=ssh_dir)
        # First migration creates the target file
        result1 = migrate(
            source=legacy_config_dir, config_manager=mgr, config_file="target"
        )
        assert len(result1.migrated) > 0

        # Second migration without force should fail
        with pytest.raises(SSHConfigError, match="already exists"):
            migrate(source=legacy_config_dir, config_manager=mgr, config_file="target")

        # With force=True it should succeed
        result2 = migrate(
            source=legacy_config_dir,
            config_manager=mgr,
            config_file="target",
            force=True,
        )
        assert len(result2.migrated) > 0
        assert not result2.errors
