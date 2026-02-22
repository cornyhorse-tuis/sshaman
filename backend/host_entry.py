"""Pydantic model for a single SSH Host block."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Directives we handle explicitly (case-insensitive keys stored lowercase).
_KNOWN_DIRECTIVES = {
    "hostname",
    "user",
    "port",
    "identityfile",
    "proxyjump",
    "forwardagent",
    "localforward",
    "remoteforward",
}


class HostEntry(BaseModel):
    """Represents a single SSH ``Host`` block in an OpenSSH config file.

    Attributes:
        name: The Host alias (value after the ``Host`` keyword).
        hostname: The ``HostName`` directive — the actual address to connect to.
        user: Optional ``User`` directive.
        port: ``Port`` directive; defaults to 22.
        identity_file: Optional ``IdentityFile`` directive.
        proxy_jump: Optional ``ProxyJump`` directive.
        forward_agent: Optional ``ForwardAgent`` directive.
        local_forwards: List of ``LocalForward`` directives (e.g. ``"8080 localhost:80"``).
        remote_forwards: List of ``RemoteForward`` directives.
        extra_options: Any SSH directives not explicitly modelled; stored as
            ``{lowercase_key: value}``.
        source_file: The ``config.d`` file this entry was read from (not
            serialised to the SSH config text).
        comment: A comment line placed directly above the ``Host`` block.
    """

    name: str
    hostname: str
    user: Optional[str] = None
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: Optional[Path] = None
    proxy_jump: Optional[str] = None
    forward_agent: Optional[bool] = None
    local_forwards: list[str] = Field(default_factory=list)
    remote_forwards: list[str] = Field(default_factory=list)
    extra_options: dict[str, str] = Field(default_factory=dict)

    # Not serialised into the SSH config text — metadata only.
    source_file: Optional[Path] = Field(default=None, exclude=True)
    comment: Optional[str] = None

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only host names."""
        if not v.strip():
            raise ValueError("Host name must not be empty")
        return v

    @field_validator("hostname")
    @classmethod
    def hostname_must_not_be_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only hostnames."""
        if not v.strip():
            raise ValueError("HostName must not be empty")
        return v

    @model_validator(mode="after")
    def extra_options_keys_are_lowercase(self) -> "HostEntry":
        """Normalise extra_options keys to lowercase."""
        # Use __dict__ to avoid triggering validate_assignment recursion.
        self.__dict__["extra_options"] = {
            k.lower(): v for k, v in self.extra_options.items()
        }
        return self

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_ssh_config(self) -> str:
        """Serialise this entry to an OpenSSH ``Host`` block string.

        Returns:
            A multi-line string representing the Host block, ready to be
            appended to a config file.  A trailing newline is included.
        """
        lines: list[str] = []

        if self.comment:
            # Ensure every comment line starts with #
            for line in self.comment.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(f"# {stripped}")
                else:
                    lines.append(stripped)

        lines.append(f"Host {self.name}")
        lines.append(f"    HostName {self.hostname}")

        if self.user is not None:
            lines.append(f"    User {self.user}")

        if self.port != 22:
            lines.append(f"    Port {self.port}")

        if self.identity_file is not None:
            lines.append(f"    IdentityFile {self.identity_file}")

        if self.proxy_jump is not None:
            lines.append(f"    ProxyJump {self.proxy_jump}")

        if self.forward_agent is not None:
            lines.append(f"    ForwardAgent {'yes' if self.forward_agent else 'no'}")

        for lf in self.local_forwards:
            lines.append(f"    LocalForward {lf}")

        for rf in self.remote_forwards:
            lines.append(f"    RemoteForward {rf}")

        for key, value in self.extra_options.items():
            # Capitalise the key for readability (e.g. usekeychain → UseKeychain)
            lines.append(f"    {key.capitalize()} {value}")

        lines.append("")  # blank line after block
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def from_ssh_config_block(
        cls,
        block_lines: list[str],
        source_file: Optional[Path] = None,
    ) -> "HostEntry":
        """Parse a list of lines belonging to one ``Host`` block.

        The first element must be the ``Host <name>`` line.  Subsequent
        lines are the indented directives.  Comment lines at the top of
        the block are collected into ``comment``.

        Args:
            block_lines: Raw lines for this block (including leading comments).
            source_file: The file this block was read from.

        Returns:
            A populated :class:`HostEntry`.

        Raises:
            ValueError: If the block does not start with a ``Host`` line or
                if required fields are missing.
        """
        comment_lines: list[str] = []
        directives: dict[str, list[str]] = {}

        host_line_found = False
        host_name: str = ""

        for raw_line in block_lines:
            line = raw_line.rstrip()

            # Collect comment lines that appear before the Host keyword
            if not host_line_found:
                stripped = line.strip()
                if stripped.startswith("#"):
                    comment_lines.append(stripped)
                    continue
                if not stripped:
                    continue  # blank lines before Host — ignore

            if not host_line_found:
                # Must be the "Host <name>" line
                stripped = line.strip()
                lower = stripped.lower()
                if not lower.startswith("host ") and lower != "host":
                    raise ValueError(
                        f"Expected 'Host <name>' line, got: {line!r}"
                    )
                host_name = stripped[5:].strip()  # everything after "Host "
                host_line_found = True
                continue

            # Directive lines (indented)
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue  # blank / inline comments

            parts = stripped.split(None, 1)
            key = parts[0].lower()
            value = parts[1] if len(parts) > 1 else ""

            if key not in directives:
                directives[key] = []
            directives[key].append(value)

        if not host_line_found or not host_name:
            raise ValueError("Block does not contain a valid 'Host <name>' line")

        # Build kwargs for the model
        kwargs: dict = {"name": host_name}

        if "hostname" in directives:
            kwargs["hostname"] = directives.pop("hostname")[0]
        else:
            # Fallback: use the alias as the hostname (valid in real SSH configs)
            kwargs["hostname"] = host_name

        if "user" in directives:
            kwargs["user"] = directives.pop("user")[0]

        if "port" in directives:
            kwargs["port"] = int(directives.pop("port")[0])

        if "identityfile" in directives:
            kwargs["identity_file"] = Path(directives.pop("identityfile")[0])

        if "proxyjump" in directives:
            kwargs["proxy_jump"] = directives.pop("proxyjump")[0]

        if "forwardagent" in directives:
            raw_fa = directives.pop("forwardagent")[0].lower()
            kwargs["forward_agent"] = raw_fa in {"yes", "true", "1"}

        if "localforward" in directives:
            kwargs["local_forwards"] = directives.pop("localforward")

        if "remoteforward" in directives:
            kwargs["remote_forwards"] = directives.pop("remoteforward")

        # Everything remaining goes into extra_options (last value wins)
        extra: dict[str, str] = {}
        for key, values in directives.items():
            extra[key] = values[-1]
        if extra:
            kwargs["extra_options"] = extra

        if comment_lines:
            kwargs["comment"] = "\n".join(comment_lines)

        entry = cls(**kwargs)
        entry.source_file = source_file
        return entry
