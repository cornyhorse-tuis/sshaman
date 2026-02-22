"""Tests for backend/host_entry.py — HostEntry model and serialisation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.host_entry import HostEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def minimal_entry(**kwargs) -> HostEntry:
    """Return a minimal valid HostEntry, merging any overrides."""
    defaults = {"name": "my-server", "hostname": "192.168.1.1"}
    defaults.update(kwargs)
    return HostEntry(**defaults)


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------

class TestHostEntryConstruction:
    def test_minimal_fields(self):
        entry = HostEntry(name="srv", hostname="10.0.0.1")
        assert entry.name == "srv"
        assert entry.hostname == "10.0.0.1"
        assert entry.port == 22
        assert entry.user is None
        assert entry.identity_file is None
        assert entry.local_forwards == []
        assert entry.remote_forwards == []
        assert entry.extra_options == {}
        assert entry.source_file is None
        assert entry.comment is None

    def test_all_fields(self):
        entry = HostEntry(
            name="full-server",
            hostname="10.0.0.2",
            user="alice",
            port=2222,
            identity_file=Path("~/.ssh/id_ed25519"),
            proxy_jump="bastion",
            forward_agent=True,
            local_forwards=["8080 localhost:80"],
            remote_forwards=["9090 localhost:90"],
            extra_options={"ServerAliveInterval": "60"},
            comment="# Production server",
        )
        assert entry.user == "alice"
        assert entry.port == 2222
        assert entry.proxy_jump == "bastion"
        assert entry.forward_agent is True
        assert entry.local_forwards == ["8080 localhost:80"]
        assert entry.extra_options == {"serveraliveinterval": "60"}  # lowercased

    def test_extra_options_keys_lowercased(self):
        entry = HostEntry(
            name="s", hostname="h",
            extra_options={"UseKeychain": "yes", "IgnoreUnknown": "UseKeychain"}
        )
        assert "usekeychain" in entry.extra_options
        assert "ignoreunknown" in entry.extra_options
        assert "UseKeychain" not in entry.extra_options

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="", hostname="10.0.0.1")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="   ", hostname="10.0.0.1")

    def test_empty_hostname_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="srv", hostname="")

    def test_whitespace_only_hostname_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="srv", hostname="  ")

    def test_port_minimum(self):
        entry = HostEntry(name="s", hostname="h", port=1)
        assert entry.port == 1

    def test_port_maximum(self):
        entry = HostEntry(name="s", hostname="h", port=65535)
        assert entry.port == 65535

    def test_port_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="s", hostname="h", port=0)

    def test_port_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            HostEntry(name="s", hostname="h", port=65536)

    def test_source_file_excluded_from_model(self):
        entry = HostEntry(name="s", hostname="h")
        entry.source_file = Path("/some/file")
        # source_file is not part of model serialisation
        dumped = entry.model_dump()
        assert "source_file" not in dumped

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            HostEntry(name="s", hostname="h", unknown_field="value")


# ---------------------------------------------------------------------------
# to_ssh_config serialisation
# ---------------------------------------------------------------------------

class TestToSshConfig:
    def test_minimal_serialisation(self):
        entry = HostEntry(name="srv", hostname="10.0.0.1")
        text = entry.to_ssh_config()
        assert "Host srv\n" in text
        assert "    HostName 10.0.0.1\n" in text
        # Port 22 should be omitted (default)
        assert "Port" not in text
        assert text.endswith("\n")

    def test_port_omitted_when_default(self):
        entry = HostEntry(name="s", hostname="h", port=22)
        assert "Port" not in entry.to_ssh_config()

    def test_port_included_when_non_default(self):
        entry = HostEntry(name="s", hostname="h", port=2222)
        assert "    Port 2222" in entry.to_ssh_config()

    def test_user_included(self):
        entry = HostEntry(name="s", hostname="h", user="alice")
        assert "    User alice" in entry.to_ssh_config()

    def test_identity_file_included(self):
        entry = HostEntry(name="s", hostname="h", identity_file=Path("~/.ssh/key"))
        assert "    IdentityFile ~/.ssh/key" in entry.to_ssh_config()

    def test_proxy_jump_included(self):
        entry = HostEntry(name="s", hostname="h", proxy_jump="bastion")
        assert "    ProxyJump bastion" in entry.to_ssh_config()

    def test_forward_agent_yes(self):
        entry = HostEntry(name="s", hostname="h", forward_agent=True)
        assert "    ForwardAgent yes" in entry.to_ssh_config()

    def test_forward_agent_no(self):
        entry = HostEntry(name="s", hostname="h", forward_agent=False)
        assert "    ForwardAgent no" in entry.to_ssh_config()

    def test_local_forward_included(self):
        entry = HostEntry(name="s", hostname="h", local_forwards=["8080 localhost:80"])
        assert "    LocalForward 8080 localhost:80" in entry.to_ssh_config()

    def test_multiple_local_forwards(self):
        entry = HostEntry(name="s", hostname="h", local_forwards=["8080 h:80", "9090 h:90"])
        text = entry.to_ssh_config()
        assert "    LocalForward 8080 h:80" in text
        assert "    LocalForward 9090 h:90" in text

    def test_remote_forward_included(self):
        entry = HostEntry(name="s", hostname="h", remote_forwards=["5555 x:5555"])
        assert "    RemoteForward 5555 x:5555" in entry.to_ssh_config()

    def test_extra_options_included(self):
        entry = HostEntry(
            name="s", hostname="h",
            extra_options={"usekeychain": "yes", "ignoreunknown": "UseKeychain"}
        )
        text = entry.to_ssh_config()
        assert "Usekeychain yes" in text
        assert "Ignoreunknown UseKeychain" in text

    def test_comment_included(self):
        entry = HostEntry(name="s", hostname="h", comment="# My server")
        text = entry.to_ssh_config()
        assert text.startswith("# My server\n")

    def test_comment_without_hash_gets_hash(self):
        entry = HostEntry(name="s", hostname="h", comment="My server")
        text = entry.to_ssh_config()
        assert "# My server" in text

    def test_multiline_comment(self):
        entry = HostEntry(name="s", hostname="h", comment="# Line 1\n# Line 2")
        text = entry.to_ssh_config()
        assert "# Line 1\n# Line 2\n" in text

    def test_trailing_blank_line(self):
        entry = HostEntry(name="s", hostname="h")
        text = entry.to_ssh_config()
        assert text.endswith("\n\n")


# ---------------------------------------------------------------------------
# from_ssh_config_block parsing
# ---------------------------------------------------------------------------

class TestFromSshConfigBlock:
    def test_minimal_block(self):
        lines = [
            "Host my-server",
            "    HostName 192.168.1.5",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.name == "my-server"
        assert entry.hostname == "192.168.1.5"

    def test_full_block(self):
        lines = [
            "Host prod",
            "    HostName 10.0.0.1",
            "    User deploy",
            "    Port 2222",
            "    IdentityFile ~/.ssh/prod_key",
            "    ProxyJump bastion",
            "    ForwardAgent yes",
            "    LocalForward 8080 localhost:80",
            "    RemoteForward 9090 localhost:90",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.name == "prod"
        assert entry.hostname == "10.0.0.1"
        assert entry.user == "deploy"
        assert entry.port == 2222
        assert entry.identity_file == Path("~/.ssh/prod_key")
        assert entry.proxy_jump == "bastion"
        assert entry.forward_agent is True
        assert entry.local_forwards == ["8080 localhost:80"]
        assert entry.remote_forwards == ["9090 localhost:90"]

    def test_forward_agent_no(self):
        lines = ["Host s", "    HostName h", "    ForwardAgent no"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.forward_agent is False

    def test_forward_agent_false_string(self):
        lines = ["Host s", "    HostName h", "    ForwardAgent false"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.forward_agent is False

    def test_comment_lines_captured(self):
        lines = [
            "# My production server",
            "Host prod",
            "    HostName 10.0.0.1",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.comment == "# My production server"

    def test_multiline_comments(self):
        lines = [
            "# Line 1",
            "# Line 2",
            "Host s",
            "    HostName h",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.comment == "# Line 1\n# Line 2"

    def test_blank_lines_before_host_ignored(self):
        lines = ["", "  ", "Host s", "    HostName h"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.name == "s"

    def test_extra_options_captured(self):
        lines = [
            "Host s",
            "    HostName h",
            "    UseKeychain yes",
            "    IgnoreUnknown UseKeychain",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.extra_options.get("usekeychain") == "yes"
        assert entry.extra_options.get("ignoreunknown") == "UseKeychain"

    def test_multiple_local_forwards(self):
        lines = [
            "Host s",
            "    HostName h",
            "    LocalForward 8080 localhost:80",
            "    LocalForward 9090 localhost:90",
        ]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.local_forwards == ["8080 localhost:80", "9090 localhost:90"]

    def test_source_file_set(self):
        p = Path("/some/file")
        lines = ["Host s", "    HostName h"]
        entry = HostEntry.from_ssh_config_block(lines, source_file=p)
        assert entry.source_file == p

    def test_inline_comment_ignored(self):
        lines = ["Host s", "    HostName h", "    # inline comment"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.hostname == "h"

    def test_blank_lines_within_block_ignored(self):
        lines = ["Host s", "", "    HostName h", ""]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.hostname == "h"

    def test_no_host_line_raises(self):
        with pytest.raises(ValueError, match="Expected 'Host <name>' line"):
            HostEntry.from_ssh_config_block(["    HostName 10.0.0.1"])

    def test_empty_lines_only_raises(self):
        with pytest.raises(ValueError):
            HostEntry.from_ssh_config_block(["", "  ", ""])

    def test_hostname_falls_back_to_alias_when_missing(self):
        """If HostName directive is absent, alias is used as the hostname."""
        lines = ["Host alias-only", "    User root"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.hostname == "alias-only"

    def test_case_insensitive_directives(self):
        lines = ["Host s", "    HOSTNAME 10.0.0.1", "    USER root", "    PORT 22"]
        entry = HostEntry.from_ssh_config_block(lines)
        assert entry.hostname == "10.0.0.1"
        assert entry.user == "root"
        assert entry.port == 22


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_minimal_round_trip(self):
        original = HostEntry(name="srv", hostname="10.0.0.1")
        text = original.to_ssh_config()
        lines = text.splitlines()
        restored = HostEntry.from_ssh_config_block(lines)
        assert restored.name == original.name
        assert restored.hostname == original.hostname
        assert restored.port == original.port

    def test_full_round_trip(self):
        original = HostEntry(
            name="prod",
            hostname="10.0.0.2",
            user="alice",
            port=2222,
            identity_file=Path("~/.ssh/prod_key"),
            proxy_jump="bastion",
            forward_agent=True,
            local_forwards=["8080 localhost:80"],
            remote_forwards=["9090 localhost:90"],
            comment="# Prod server",
        )
        text = original.to_ssh_config()
        lines = text.splitlines()
        restored = HostEntry.from_ssh_config_block(lines)
        assert restored.name == original.name
        assert restored.hostname == original.hostname
        assert restored.user == original.user
        assert restored.port == original.port
        assert restored.identity_file == original.identity_file
        assert restored.proxy_jump == original.proxy_jump
        assert restored.forward_agent == original.forward_agent
        assert restored.local_forwards == original.local_forwards
        assert restored.remote_forwards == original.remote_forwards

    def test_extra_options_round_trip(self):
        original = HostEntry(
            name="mac",
            hostname="10.0.0.3",
            extra_options={"usekeychain": "yes"},
        )
        text = original.to_ssh_config()
        lines = text.splitlines()
        restored = HostEntry.from_ssh_config_block(lines)
        assert "usekeychain" in restored.extra_options
