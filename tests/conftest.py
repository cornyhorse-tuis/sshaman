"""Shared pytest fixtures for SSHaMan tests.

All tests that touch the filesystem must use these fixtures — never
write to real ``~/.ssh/`` or ``~/.config/sshaman/`` paths in tests.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from backend.manager import SSHManager
from backend.ssh_config import SSHConfigManager


# ---------------------------------------------------------------------------
# SSH directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ssh_dir(tmp_path: Path) -> Path:
    """Return a temporary ~/.ssh/ equivalent with config.d/ already created.

    The main ``config`` file is pre-populated with the Include directive.
    Use this fixture whenever you need a clean, empty SSH environment.
    """
    ssh = tmp_path / ".ssh"
    ssh.mkdir(mode=0o700)

    config_d = ssh / "config.d"
    config_d.mkdir(mode=0o700)

    config = ssh / "config"
    config.write_text("Include ~/.ssh/config.d/*\n", encoding="utf-8")
    config.chmod(0o600)

    return ssh


@pytest.fixture
def sample_ssh_dir(ssh_dir: Path) -> Path:
    """Return a temporary SSH dir with two pre-populated config.d files.

    ``test-hosts`` contains:
      - ``web-server``  (192.168.1.100, user=admin, port=22, identity=~/.ssh/id_rsa)
      - ``db-server``   (192.168.1.101, user=postgres, port=5432)

    ``extra-hosts`` contains:
      - ``jump-box``    (10.0.0.1, user=ops, port=22)
    """
    test_hosts = ssh_dir / "config.d" / "test-hosts"
    test_hosts.write_text(
        "# Test hosts file\n"
        "\n"
        "Host web-server\n"
        "    HostName 192.168.1.100\n"
        "    User admin\n"
        "    Port 22\n"
        "    IdentityFile ~/.ssh/id_rsa\n"
        "\n"
        "Host db-server\n"
        "    HostName 192.168.1.101\n"
        "    User postgres\n"
        "    Port 5432\n"
        "\n",
        encoding="utf-8",
    )
    test_hosts.chmod(0o600)

    extra_hosts = ssh_dir / "config.d" / "extra-hosts"
    extra_hosts.write_text(
        "Host jump-box\n    HostName 10.0.0.1\n    User ops\n    Port 22\n\n",
        encoding="utf-8",
    )
    extra_hosts.chmod(0o600)

    return ssh_dir


# ---------------------------------------------------------------------------
# Manager / config-manager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_manager(sample_ssh_dir: Path) -> SSHConfigManager:
    """Return an SSHConfigManager pointed at the sample SSH dir."""
    return SSHConfigManager(ssh_dir=sample_ssh_dir)


@pytest.fixture
def empty_config_manager(ssh_dir: Path) -> SSHConfigManager:
    """Return an SSHConfigManager pointed at an empty SSH dir (no hosts)."""
    return SSHConfigManager(ssh_dir=ssh_dir)


@pytest.fixture
def manager(sample_ssh_dir: Path) -> SSHManager:
    """Return an SSHManager pointed at the sample SSH dir."""
    return SSHManager(ssh_dir=sample_ssh_dir)


@pytest.fixture
def empty_manager(ssh_dir: Path) -> SSHManager:
    """Return an SSHManager pointed at an empty SSH dir."""
    return SSHManager(ssh_dir=ssh_dir)


# ---------------------------------------------------------------------------
# Legacy JSON config fixtures (for migration tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_config_dir(tmp_path: Path) -> Path:
    """Create a legacy ~/.config/sshaman/ directory structure with JSON files.

    Structure:
        group1/
            vm1.json   (alias=vm1, has identity_file + forward_ports)
            vm2.json   (alias=vm2, has password — should be dropped)
        group2/
            vm3.json   (alias=vm3, minimal fields)
    """
    base = tmp_path / ".config" / "sshaman"
    group1 = base / "group1"
    group1.mkdir(parents=True)
    group2 = base / "group2"
    group2.mkdir()

    (group1 / "vm1.json").write_text(
        '{"alias": "vm1", "host": "192.168.1.100", "port": 22, '
        '"user": "root", "identity_file": "~/.ssh/id_rsa", '
        '"forward_ports": ["8080:localhost:80", ""], '
        '"start_commands": [], "server_group_path": "/tmp/group1"}',
        encoding="utf-8",
    )

    (group1 / "vm2.json").write_text(
        '{"alias": "vm2", "host": "192.168.1.101", "port": 2222, '
        '"user": "deploy", "identity_file": null, '
        '"password": "s3cr3t", "forward_ports": [], '
        '"start_commands": ["echo hi"], "server_group_path": "/tmp/group1"}',
        encoding="utf-8",
    )

    (group2 / "vm3.json").write_text(
        '{"alias": "vm3", "host": "10.0.0.5", "port": 22, '
        '"user": "ubuntu", "identity_file": null, '
        '"forward_ports": [], "start_commands": [], '
        '"server_group_path": "/tmp/group2"}',
        encoding="utf-8",
    )

    return base
