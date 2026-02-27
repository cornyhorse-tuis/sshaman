"""Migrate legacy SSHaMan JSON configs to native SSH config format.

The old storage format was a directory tree at ``~/.config/sshaman/`` where
each server was a JSON file.  This module reads those files and converts
them to ``Host`` blocks written to ``~/.ssh/config.d/<config_file>``.

Dropped fields (with warnings):
    - ``password`` — SSH passwords should never be stored on disk.
    - ``start_commands`` — not a native SSH config concept.
    - ``server_group_path`` — internal metadata, irrelevant after migration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.host_entry import HostEntry
from backend.ssh_config import SSHConfigManager, SSHConfigError

# Default source directory for the old SSHaMan config store.
_DEFAULT_SOURCE = Path.home() / ".config" / "sshaman"

# Config.d filename used when no explicit target is provided.
_DEFAULT_TARGET_FILE = "sshaman-migrated"


@dataclass
class MigrationResult:
    """Summary of a migration run.

    Attributes:
        migrated: Successfully converted entries.
        warnings: Non-fatal warnings per host alias.
        errors: Fatal per-file errors that prevented conversion.
        dry_run: Whether the migration was a dry run (nothing written).
    """

    migrated: list[HostEntry] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    source_cleanup_reminder: str = ""


def discover_json_configs(source: Path) -> list[tuple[Path, dict]]:
    """Walk ``source`` recursively and return all valid JSON server configs.

    A valid config is a ``.json`` file that can be loaded as a dict.

    Args:
        source: Root directory of the legacy SSHaMan config store.

    Returns:
        List of ``(path, data)`` tuples.
    """
    results: list[tuple[Path, dict]] = []
    for json_file in sorted(source.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                results.append((json_file, data))
        except (json.JSONDecodeError, OSError):
            pass  # Malformed / unreadable files are ignored here; errors
            # are reported by the caller via convert_json_to_host_entry
    return results


def convert_json_to_host_entry(
    json_path: Path,
    data: dict,
    source_root: Path,
) -> tuple[HostEntry, list[str]]:
    """Convert a single legacy JSON dict to a :class:`~backend.host_entry.HostEntry`.

    Args:
        json_path: Path of the JSON file (used to compute the comment).
        data: Parsed JSON content.
        source_root: Root of the legacy config store (for relative-path comment).

    Returns:
        ``(entry, warnings)`` where *warnings* is a list of human-readable
        messages about dropped fields.

    Raises:
        KeyError: If required fields (``alias``, ``host``) are absent.
        ValueError: If field values are invalid (e.g. bad port).
    """
    warnings: list[str] = []
    alias = data["alias"]

    if data.get("password"):
        warnings.append(
            f"{alias!r}: 'password' field dropped — store credentials in "
            "an SSH key or ssh-agent instead."
        )

    if data.get("start_commands"):
        warnings.append(
            f"{alias!r}: 'start_commands' not migrated — SSH config does not "
            "support arbitrary remote commands at connection time."
        )

    # Build the comment from group path
    try:
        rel = json_path.parent.relative_to(source_root)
        comment_text = (
            f"# Migrated from {rel}/" if str(rel) != "." else "# Migrated by SSHaMan"
        )
    except ValueError:
        comment_text = "# Migrated by SSHaMan"

    local_forwards: list[str] = [fp for fp in (data.get("forward_ports") or []) if fp]

    entry = HostEntry(
        name=alias,
        hostname=data["host"],
        user=data.get("user") or None,
        port=int(data.get("port", 22)),
        identity_file=Path(data["identity_file"])
        if data.get("identity_file")
        else None,
        local_forwards=local_forwards,
        comment=comment_text,
    )

    return entry, warnings


def migrate(
    source: Optional[Path] = None,
    config_manager: Optional[SSHConfigManager] = None,
    config_file: str = _DEFAULT_TARGET_FILE,
    dry_run: bool = False,
    force: bool = False,
) -> MigrationResult:
    """Run the migration from the legacy JSON store to SSH config format.

    Args:
        source: Path to the old SSHaMan directory.  Defaults to
            ``~/.config/sshaman``.
        config_manager: :class:`~backend.ssh_config.SSHConfigManager`
            instance to write to.  A default instance (``~/.ssh``) is
            created when ``None``.
        config_file: Name of the target ``config.d`` file.
        dry_run: If ``True``, parse and validate but do not write anything.
        force: If ``True``, allow writing to an existing target file.

    Returns:
        A :class:`MigrationResult` describing what happened.

    Raises:
        SSHConfigError: If ``dry_run`` is ``False``, ``force`` is ``False``,
            and the target config file already exists.
    """
    source = source or _DEFAULT_SOURCE
    mgr = config_manager or SSHConfigManager()
    result = MigrationResult(dry_run=dry_run)

    if not source.exists():
        return result  # Nothing to migrate

    if not dry_run:
        mgr.ensure_config_d_setup()
        target_path = mgr.config_d / config_file
        if target_path.exists() and not force:
            raise SSHConfigError(
                f"Target config file already exists: {target_path}. "
                "Use force=True to overwrite."
            )

    raw_configs = discover_json_configs(source)

    seen_aliases: set[str] = set()

    for json_path, data in raw_configs:
        try:
            entry, warns = convert_json_to_host_entry(json_path, data, source)
        except (KeyError, ValueError, TypeError) as exc:
            result.errors[str(json_path)] = str(exc)
            continue

        if warns:
            result.warnings[entry.name] = warns

        # Deduplicate aliases
        original_name = entry.name
        counter = 2
        while entry.name in seen_aliases:
            entry = entry.model_copy(update={"name": f"{original_name}-{counter}"})
            result.warnings.setdefault(entry.name, []).append(
                f"Alias {original_name!r} was already used; renamed to {entry.name!r}."
            )
            counter += 1

        seen_aliases.add(entry.name)
        result.migrated.append(entry)

    if not dry_run:
        for entry in result.migrated:
            mgr.write_host(entry, config_file)

    if not dry_run and result.migrated:
        result.source_cleanup_reminder = (
            f"Legacy configs remain at {source}. "
            "If any contained passwords, securely delete them: "
            f"  rm -rf {source}"
        )

    return result
