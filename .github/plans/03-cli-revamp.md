# Phase 2: CLI Revamp

> **Status**: Not started  
> **Depends on**: Phase 1 (Backend)  
> **Blocks**: Nothing (can be done in parallel with Phase 3)

---

## Overview

Rewrite the CLI to use the new backend (`backend/manager.py`) and provide a complete set of commands for managing SSH hosts and config files.

---

## Current CLI Problems

1. Two conflicting `cli()` group definitions (one is dead code)
2. `list-all` ignores the `--config_path` argument
3. `add-server` accepts `--password` (security risk)
4. No `edit`, `remove`, `search`, `show`, or `connect` commands
5. No `config-file` management commands
6. `initialize-sample` creates test data in the real filesystem
7. Error handling is nonexistent — raw tracebacks on failure
8. Group-based hierarchy (`group.subgroup`) doesn't map to the new `config.d` model

---

## New CLI Design

### Top-level structure

```
sshaman                          → Launch TUI (no subcommand)
sshaman list [--filter PATTERN]  → List all hosts
sshaman show HOST                → Show detailed config for a host
sshaman add HOST                 → Add a new host (interactive prompts for details)
sshaman edit HOST                → Edit an existing host
sshaman remove HOST              → Remove a host (with confirmation)
sshaman connect HOST             → SSH to a host
sshaman sftp HOST                → SFTP to a host
sshaman search PATTERN           → Search hosts by name, hostname, or user

sshaman config list              → List config.d files
sshaman config create NAME       → Create a new config.d file
sshaman config delete NAME       → Delete a config.d file
sshaman config show NAME         → Show contents of a config.d file
sshaman config init              → Ensure ~/.ssh/config.d/ exists and Include is set
```

### Implementation

```python
# cli/sshaman_cli.py

import click
from pathlib import Path
from backend.manager import SSHManager
from backend.host_entry import HostEntry

@click.group(invoke_without_command=True)
@click.option('--ssh-dir', type=click.Path(path_type=Path), default=None,
              help='Override SSH directory (default: ~/.ssh)')
@click.pass_context
def cli(ctx, ssh_dir):
    """SSHaMan — SSH connection manager."""
    ctx.ensure_object(dict)
    ctx.obj['manager'] = SSHManager(ssh_dir=ssh_dir)
    if ctx.invoked_subcommand is None:
        # Launch TUI
        from tui.app import SSHaManApp
        app = SSHaManApp(manager=ctx.obj['manager'])
        app.run()


@cli.command()
@click.option('--filter', '-f', 'pattern', default=None, help='Filter hosts by pattern')
@click.pass_context
def list(ctx, pattern):
    """List all SSH hosts."""
    manager = ctx.obj['manager']
    hosts = manager.list_hosts(filter=pattern)
    # Format and display with Rich table
    ...


@cli.command()
@click.argument('host')
@click.pass_context
def show(ctx, host):
    """Show detailed configuration for a host."""
    ...


@cli.command()
@click.argument('name')
@click.option('--hostname', '-H', required=True, help='Server address')
@click.option('--user', '-u', default=None, help='Username')
@click.option('--port', '-p', default=22, help='Port number')
@click.option('--identity-file', '-i', default=None, help='Path to SSH key')
@click.option('--config-file', '-c', default='sshaman-hosts', help='Config file in config.d/')
@click.pass_context
def add(ctx, name, hostname, user, port, identity_file, config_file):
    """Add a new SSH host."""
    ...


@cli.command()
@click.argument('host')
@click.pass_context
def edit(ctx, host):
    """Edit an existing SSH host."""
    ...


@cli.command()
@click.argument('host')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
@click.pass_context
def remove(ctx, host):
    """Remove an SSH host."""
    ...


@cli.command()
@click.argument('host')
@click.pass_context
def connect(ctx, host):
    """Connect to a host via SSH."""
    import os
    manager = ctx.obj['manager']
    cmd = manager.connect_command(host)
    os.execvp('ssh', cmd.split())


@cli.command()
@click.argument('host')
@click.pass_context  
def sftp(ctx, host):
    """Connect to a host via SFTP."""
    ...


@cli.command()
@click.argument('pattern')
@click.pass_context
def search(ctx, pattern):
    """Search hosts by name, hostname, or user."""
    ...


# Subgroup for config file management
@cli.group()
def config():
    """Manage SSH config files in config.d/."""
    pass

@config.command('list')
@click.pass_context
def config_list(ctx):
    """List all config.d files."""
    ...

@config.command('create')
@click.argument('name')
@click.pass_context
def config_create(ctx, name):
    """Create a new config.d file."""
    ...

@config.command('delete')
@click.argument('name')
@click.option('--yes', '-y', is_flag=True)
@click.pass_context
def config_delete(ctx, name):
    """Delete a config.d file."""
    ...

@config.command('init')
@click.pass_context
def config_init(ctx):
    """Initialize config.d setup (create dir, add Include)."""
    ...
```

---

## Key Design Decisions

1. **`--ssh-dir` global option** replaces `--config_path` — lets tests pass a tmp directory
2. **No `--password` option** anywhere — security-first
3. **`connect` uses `os.execvp`** — replaces the process with SSH instead of subprocess
4. **`config` subgroup** — clean namespace for config.d file management
5. **No group/subgroup hierarchy** — the `config.d` file *is* the organizational unit
6. **Rich formatting** — use `rich.table.Table` for `list`, `rich.panel.Panel` for `show`
7. **Click context** — pass `SSHManager` via Click context, not global imports

---

## Tasks

- [ ] Remove old `cli/sshaman_cli.py` content
- [ ] Implement new CLI with all commands above
- [ ] Add `--ssh-dir` support for testing
- [ ] Use Rich for formatted output
- [ ] Add proper error handling with `click.echo` and `ctx.exit(1)`
- [ ] Update `entrypoint.py` to use the new CLI
- [ ] Test all commands with `CliRunner` using tmp directories — target 98%+ coverage
- [ ] Test error paths: missing host, invalid args, filesystem errors
- [ ] Test `--yes` flag skips confirmation, absence prompts confirmation
- [ ] Mark `os.execvp` calls with `# pragma: no cover — replaces process`
- [ ] Mark `if __name__` guard with `# pragma: no cover`
