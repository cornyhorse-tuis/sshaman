"""High-level SSH config management operations.

Both the CLI and TUI call this module exclusively — neither layer reads
SSH config files directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.host_entry import HostEntry
from backend.ssh_config import SSHConfigError, SSHConfigManager

# Default config.d filename used when no explicit file is specified.
_DEFAULT_CONFIG_FILE = "sshaman-hosts"


class HostNotFoundError(SSHConfigError):
    """Raised when a requested host alias does not exist."""


class DuplicateHostError(SSHConfigError):
    """Raised when adding a host whose alias already exists."""


class ConfigFileExistsError(SSHConfigError):
    """Raised when creating a config file that already exists."""


class SSHManager:
    """High-level SSH config management operations.

    This is the single API used by both the CLI and TUI.  It delegates
    all file I/O to :class:`~backend.ssh_config.SSHConfigManager`.

    Args:
        ssh_dir: Path to the ``.ssh`` directory.  Defaults to ``~/.ssh``.
    """

    def __init__(self, ssh_dir: Optional[Path] = None) -> None:
        self._config = SSHConfigManager(ssh_dir)

    # ------------------------------------------------------------------
    # Host queries
    # ------------------------------------------------------------------

    def list_hosts(self, filter: Optional[str] = None) -> list[HostEntry]:
        """Return all SSH hosts, optionally filtered.

        Args:
            filter: Case-insensitive substring matched against the host
                alias, hostname, and user.  ``None`` returns all hosts.

        Returns:
            List of :class:`~backend.host_entry.HostEntry` in config-file
            order.
        """
        hosts = self._config.read_all_hosts()
        if filter is None:
            return hosts

        q = filter.lower()
        return [
            h
            for h in hosts
            if q in h.name.lower()
            or q in h.hostname.lower()
            or (h.user and q in h.user.lower())
        ]

    def get_host(self, name: str) -> Optional[HostEntry]:
        """Return a single host by its alias, or ``None`` if not found.

        Args:
            name: The ``Host`` alias to look up.

        Returns:
            The matching :class:`~backend.host_entry.HostEntry` or ``None``.
        """
        for host in self._config.read_all_hosts():
            if host.name == name:
                return host
        return None

    # ------------------------------------------------------------------
    # Host mutations
    # ------------------------------------------------------------------

    def add_host(
        self,
        entry: HostEntry,
        config_file: str = _DEFAULT_CONFIG_FILE,
    ) -> None:
        """Add a new host to a ``config.d`` file.

        Args:
            entry: The host entry to add.
            config_file: Filename inside ``config.d/``.  Defaults to
                ``"sshaman-hosts"``.

        Raises:
            DuplicateHostError: If a host with the same alias already exists.
        """
        if self.get_host(entry.name) is not None:
            raise DuplicateHostError(
                f"A host named {entry.name!r} already exists. "
                "Use edit_host() to modify it."
            )
        self._config.write_host(entry, config_file)

    def edit_host(self, name: str, **updates) -> HostEntry:
        """Update fields on an existing host and persist the change.

        Args:
            name: Alias of the host to edit.
            **updates: Field names and their new values.  Accepted fields
                correspond to :class:`~backend.host_entry.HostEntry`
                attributes (e.g. ``hostname``, ``user``, ``port``).

        Returns:
            The updated :class:`~backend.host_entry.HostEntry`.

        Raises:
            HostNotFoundError: If no host with ``name`` exists.
        """
        existing = self.get_host(name)
        if existing is None:
            raise HostNotFoundError(f"Host not found: {name!r}")

        updated = existing.model_copy(update=updates)
        self._config.update_host(name, updated)
        return updated

    def remove_host(self, name: str) -> None:
        """Remove a host by alias.

        Args:
            name: The ``Host`` alias to remove.

        Raises:
            HostNotFoundError: If no host with ``name`` exists.
        """
        if self.get_host(name) is None:
            raise HostNotFoundError(f"Host not found: {name!r}")
        self._config.remove_host(name)

    # ------------------------------------------------------------------
    # Connection commands
    # ------------------------------------------------------------------

    def connect_command(self, name: str) -> list[str]:
        """Build an SSH argv list for the named host.

        Because the host lives in ``~/.ssh/config`` (via the ``Include``
        directive) SSH resolves it by alias natively, so the command is
        simply ``["ssh", "<alias>"]``.

        Args:
            name: The ``Host`` alias.

        Returns:
            A list suitable for passing to ``os.execvp`` or ``subprocess``.

        Raises:
            HostNotFoundError: If no host with ``name`` exists.
        """
        if self.get_host(name) is None:
            raise HostNotFoundError(f"Host not found: {name!r}")
        # Use "--" to prevent a host alias starting with "-" from being
        # interpreted as an SSH option flag.
        return ["ssh", "--", name]

    def sftp_command(self, name: str) -> list[str]:
        """Build an SFTP argv list for the named host.

        Args:
            name: The ``Host`` alias.

        Returns:
            A list suitable for ``os.execvp``.

        Raises:
            HostNotFoundError: If no host with ``name`` exists.
        """
        if self.get_host(name) is None:
            raise HostNotFoundError(f"Host not found: {name!r}")
        return ["sftp", "--", name]

    # ------------------------------------------------------------------
    # Config-file management
    # ------------------------------------------------------------------

    def list_config_files(self) -> list[Path]:
        """Return all files in ``config.d/``.

        Returns:
            Sorted list of :class:`~pathlib.Path` objects.
        """
        return self._config.list_config_files()

    def create_config_file(self, name: str) -> Path:
        """Create a new empty ``config.d`` file.

        Args:
            name: Filename such as ``"20-home-lab"``.

        Returns:
            Path to the newly created file.

        Raises:
            SSHConfigError: If the file already exists or the name is invalid.
        """
        return self._config.create_config_file(name)

    def delete_config_file(self, name: str) -> None:
        """Delete a ``config.d`` file.

        Args:
            name: Filename to delete.

        Raises:
            SSHConfigError: If the file does not exist.
        """
        self._config.delete_config_file(name)

    def ensure_setup(self) -> None:
        """Ensure ``config.d/`` exists and ``~/.ssh/config`` has the ``Include``.

        Safe to call multiple times — idempotent.
        """
        self._config.ensure_config_d_setup()
