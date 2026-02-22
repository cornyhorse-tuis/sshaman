"""Low-level SSH config file I/O — reads and writes ~/.ssh/config and config.d/*.

This module is intentionally side-effect-free in its methods (no printing,
no interactive prompts).  All filesystem mutations are explicit.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from backend.host_entry import HostEntry

# The Include directive SSHaMan manages inside ~/.ssh/config.
_INCLUDE_DIRECTIVE = "Include ~/.ssh/config.d/*"

# Permissions for SSH-managed files and directories.
_FILE_MODE = 0o600
_DIR_MODE = 0o700


class SSHConfigError(Exception):
    """Raised when an SSH config operation cannot be completed safely."""


class SSHConfigManager:
    """Low-level SSH config file operations.

    All methods operate on the SSH directory passed at construction time,
    defaulting to ``~/.ssh``.  Pass a ``tmp_path``-based directory in tests
    to avoid touching the real filesystem.

    Args:
        ssh_dir: Path to the ``.ssh`` directory.  Defaults to ``~/.ssh``.
    """

    def __init__(self, ssh_dir: Optional[Path] = None) -> None:
        self.ssh_dir: Path = ssh_dir or (Path.home() / ".ssh")
        self.config_file: Path = self.ssh_dir / "config"
        self.config_d: Path = self.ssh_dir / "config.d"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def ensure_config_d_setup(self) -> None:
        """Create ``config.d/`` and add the ``Include`` directive if missing.

        This is the only method that touches ``~/.ssh/config`` directly.
        It appends a single line and never removes or rewrites existing
        content.

        Raises:
            SSHConfigError: If the SSH directory does not exist and cannot
                be created.
        """
        # Ensure the .ssh directory exists with correct permissions
        if not self.ssh_dir.exists():
            self.ssh_dir.mkdir(parents=True, mode=_DIR_MODE)

        _set_permissions(self.ssh_dir, _DIR_MODE)

        # Ensure config.d/ exists
        if not self.config_d.exists():
            self.config_d.mkdir(mode=_DIR_MODE)

        _set_permissions(self.config_d, _DIR_MODE)

        # Ensure main config file exists
        if not self.config_file.exists():
            self.config_file.touch()
            _set_permissions(self.config_file, _FILE_MODE)

        # Ensure Include directive is present
        existing = self.config_file.read_text(encoding="utf-8")
        if _INCLUDE_DIRECTIVE not in existing:
            # Prepend so it takes effect before any other rules
            new_content = _INCLUDE_DIRECTIVE + "\n\n" + existing
            self._safe_write(self.config_file, new_content)

    # ------------------------------------------------------------------
    # Config-file management
    # ------------------------------------------------------------------

    def list_config_files(self) -> list[Path]:
        """Return a sorted list of files inside ``config.d/``.

        Returns:
            Sorted list of :class:`~pathlib.Path` objects (files only).
        """
        if not self.config_d.exists():
            return []
        return sorted(
            p for p in self.config_d.iterdir() if p.is_file()
        )

    def create_config_file(self, name: str) -> Path:
        """Create a new empty file in ``config.d/`` with correct permissions.

        Args:
            name: Filename (not a path) such as ``"10-work-servers"``.

        Returns:
            The :class:`~pathlib.Path` of the created file.

        Raises:
            SSHConfigError: If ``name`` contains path separators or a file
                with that name already exists.
        """
        if os.sep in name or "/" in name:
            raise SSHConfigError(
                f"Config file name must not contain path separators: {name!r}"
            )

        self.ensure_config_d_setup()
        path = self.config_d / name

        if path.exists():
            raise SSHConfigError(
                f"Config file already exists: {path}"
            )

        path.touch()
        _set_permissions(path, _FILE_MODE)
        return path

    def delete_config_file(self, name: str) -> None:
        """Delete a file from ``config.d/``.

        Args:
            name: Filename (not a path).

        Raises:
            SSHConfigError: If the file does not exist.
        """
        path = self.config_d / name
        if not path.exists():
            raise SSHConfigError(
                f"Config file does not exist: {path}"
            )
        path.unlink()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_all_hosts(self) -> list[HostEntry]:
        """Parse all Host blocks from every file in ``config.d/``.

        Returns:
            A flat list of :class:`~backend.host_entry.HostEntry` objects in
            file-alphabetical order.
        """
        hosts: list[HostEntry] = []
        for path in self.list_config_files():
            hosts.extend(self.read_hosts_from_file(path))
        return hosts

    def read_hosts_from_file(self, path: Path) -> list[HostEntry]:
        """Parse all ``Host`` blocks from a single config file.

        Wildcard (``Host *``) and ``Match`` blocks are skipped silently.

        Args:
            path: Path to an SSH config file.

        Returns:
            List of :class:`~backend.host_entry.HostEntry` objects found.
        """
        if not path.exists():
            raise SSHConfigError(f"Config file not found: {path}")

        text = path.read_text(encoding="utf-8")
        blocks = _split_into_blocks(text, path)
        return blocks

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def write_host(self, entry: HostEntry, config_file_name: str) -> None:
        """Append a Host block to a ``config.d`` file.

        Creates the file if it does not yet exist.

        Args:
            entry: The :class:`~backend.host_entry.HostEntry` to write.
            config_file_name: Filename inside ``config.d/``
                (e.g. ``"sshaman-hosts"``).
        """
        self.ensure_config_d_setup()
        path = self.config_d / config_file_name

        if not path.exists():
            path.touch()
            _set_permissions(path, _FILE_MODE)

        existing = path.read_text(encoding="utf-8")
        # Ensure there's a blank line separator before new block
        separator = "\n" if existing and not existing.endswith("\n\n") else ""
        new_content = existing + separator + entry.to_ssh_config()
        self._safe_write(path, new_content)

    def remove_host(self, host_name: str) -> None:
        """Remove a ``Host`` block by name from whichever ``config.d`` file contains it.

        Args:
            host_name: The ``Host`` alias to remove.

        Raises:
            SSHConfigError: If no host with that name is found in any
                ``config.d`` file.
        """
        for path in self.list_config_files():
            hosts = self.read_hosts_from_file(path)
            names = [h.name for h in hosts]
            if host_name in names:
                self._remove_host_from_file(host_name, path)
                return

        raise SSHConfigError(f"Host not found: {host_name!r}")

    def update_host(self, host_name: str, entry: HostEntry) -> None:
        """Replace an existing ``Host`` block in-place with ``entry``.

        Args:
            host_name: The current alias of the host to replace.
            entry: The updated :class:`~backend.host_entry.HostEntry`.

        Raises:
            SSHConfigError: If no host with ``host_name`` is found.
        """
        for path in self.list_config_files():
            hosts = self.read_hosts_from_file(path)
            if any(h.name == host_name for h in hosts):
                self._remove_host_from_file(host_name, path)
                existing = path.read_text(encoding="utf-8")
                separator = "\n" if existing and not existing.endswith("\n\n") else ""
                self._safe_write(path, existing + separator + entry.to_ssh_config())
                return

        raise SSHConfigError(f"Host not found: {host_name!r}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_host_from_file(self, host_name: str, path: Path) -> None:
        """Rewrite ``path`` with the named ``Host`` block stripped out.

        Args:
            host_name: Alias of the block to remove.
            path: The file to edit.
        """
        text = path.read_text(encoding="utf-8")
        new_text = _remove_block_from_text(text, host_name)
        self._safe_write(path, new_text)

    @staticmethod
    def _safe_write(path: Path, content: str) -> None:
        """Atomically write ``content`` to ``path`` and restore permissions.

        Args:
            path: Destination file.
            content: Text to write.
        """
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
        _set_permissions(path, _FILE_MODE)


# ---------------------------------------------------------------------------
# Module-level parsing helpers
# ---------------------------------------------------------------------------

def _set_permissions(path: Path, mode: int) -> None:
    """Set ``mode`` on ``path`` if it differs from the current permissions.

    Args:
        path: File or directory to chmod.
        mode: Desired permission bits.
    """
    current = stat.S_IMODE(path.stat().st_mode)
    if current != mode:
        path.chmod(mode)


def _split_into_blocks(text: str, source_file: Path) -> list[HostEntry]:
    """Split raw SSH config text into :class:`~backend.host_entry.HostEntry` objects.

    Only ``Host <name>`` blocks with a concrete alias (not ``Host *``) are
    returned.  ``Match`` blocks and global directives are skipped.

    Args:
        text: Full contents of an SSH config file.
        source_file: Used to populate :attr:`~backend.host_entry.HostEntry.source_file`.

    Returns:
        List of parsed :class:`~backend.host_entry.HostEntry` objects.
    """
    entries: list[HostEntry] = []
    lines = text.splitlines()

    # Gather pending comment lines that precede the next Host block
    pending_comments: list[str] = []
    current_block: list[str] = []
    in_block = False

    def _flush_block() -> None:
        if not current_block:
            return
        try:
            entry = HostEntry.from_ssh_config_block(current_block, source_file=source_file)
            entries.append(entry)
        except (ValueError, Exception):
            pass  # Malformed blocks are skipped silently

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        # Detect the start of a new Host or Match block
        is_host_start = lower.startswith("host ") or lower == "host"
        is_match_start = lower.startswith("match ")

        if is_host_start or is_match_start:
            # Flush previous block
            if in_block:
                _flush_block()
                current_block = []
                pending_comments = []

            if is_match_start:
                in_block = False
                pending_comments = []
                continue

            # Start new Host block — prepend accumulated comments
            host_alias = stripped[5:].strip() if lower.startswith("host ") else ""

            # Skip wildcard entries — they're global settings, not specific hosts
            if host_alias == "*":
                in_block = False
                pending_comments = []
                continue

            in_block = True
            current_block = pending_comments + [line]
            pending_comments = []
            continue

        if in_block:
            current_block.append(line)
        else:
            # Outside any block — collect comment lines for the next Host block
            if stripped.startswith("#"):
                pending_comments.append(line)
            elif stripped:
                # A non-comment global line resets pending comments
                pending_comments = []
            # blank lines outside blocks are ignored

    # Flush the last block
    _flush_block()

    return entries


def _remove_block_from_text(text: str, host_name: str) -> str:
    """Return ``text`` with the ``Host <host_name>`` block removed.

    The block extends from the ``Host`` line (or its preceding comments) to
    the line before the next ``Host``/``Match`` line or end of file.  The
    blank line separating blocks is also removed.

    Args:
        text: Full SSH config file content.
        host_name: Alias to remove.

    Returns:
        Modified file content.
    """
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    skip = False
    pending: list[str] = []  # comment lines before a Host block

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        lower = stripped.lower()

        is_host = lower.startswith("host ") or lower == "host"
        is_match = lower.startswith("match ")

        if is_host or is_match:
            alias = stripped[5:].strip() if lower.startswith("host ") else ""
            if is_host and alias == host_name:
                # Discard pending comments that belong to this block
                pending = []
                skip = True
                i += 1
                continue
            else:
                # Flush pending comments (they belong to this other block)
                result.extend(pending)
                pending = []
                skip = False
                result.append(raw)
                i += 1
                continue

        if skip:
            # Inside the block we're removing — drop content but stop at blank lines
            # between blocks (a blank line after the removed block should be consumed)
            if not stripped:
                skip = False  # consume one trailing blank line
            i += 1
            continue

        if stripped.startswith("#"):
            pending.append(raw)
        elif not stripped:
            # Blank line flushes pending and passes through
            result.extend(pending)
            pending = []
            result.append(raw)
        else:
            result.extend(pending)
            pending = []
            result.append(raw)

        i += 1

    # Flush any trailing pending comments
    result.extend(pending)

    return "".join(result)
