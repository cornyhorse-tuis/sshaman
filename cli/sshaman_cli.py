"""SSHaMan CLI — all commands call backend/manager.py exclusively."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.host_entry import HostEntry
from backend.manager import (
    DuplicateHostError,
    HostNotFoundError,
    SSHManager,
)
from backend.ssh_config import SSHConfigError

console = Console()
err_console = Console(stderr=True, style="bold red")


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.option(
    "--ssh-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="SSHAMAN_SSH_DIR",
    help="Override the SSH directory (default: ~/.ssh).",
)
@click.pass_context
def cli(ctx: click.Context, ssh_dir: Optional[Path]) -> None:
    """SSHaMan — manage SSH connections and config files."""
    ctx.ensure_object(dict)
    ctx.obj["manager"] = SSHManager(ssh_dir=ssh_dir)

    if ctx.invoked_subcommand is None:
        # No subcommand → launch TUI
        from tui.app import SSHaManApp

        app = SSHaManApp(manager=ctx.obj["manager"])
        result = app.run()

        if result:
            action, host_name = result
            mgr: SSHManager = ctx.obj["manager"]
            if action == "ssh":
                cmd = mgr.connect_command(host_name)
                os.execvp(cmd[0], cmd)  # pragma: no cover — replaces process
            elif action == "sftp":
                cmd = mgr.sftp_command(host_name)
                os.execvp(cmd[0], cmd)  # pragma: no cover — replaces process


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@cli.command("list")
@click.option(
    "--filter", "-f", "pattern", default=None, help="Filter by name, hostname, or user."
)
@click.pass_context
def list_hosts(ctx: click.Context, pattern: Optional[str]) -> None:
    """List all SSH hosts."""
    mgr: SSHManager = ctx.obj["manager"]
    hosts = mgr.list_hosts(filter=pattern)

    if not hosts:
        console.print("[dim]No hosts found.[/dim]")
        return

    table = Table(title="SSH Hosts", show_header=True, header_style="bold cyan")
    table.add_column("Host Alias", style="bold")
    table.add_column("HostName")
    table.add_column("User")
    table.add_column("Port", justify="right")
    table.add_column("Config File", style="dim")

    for h in hosts:
        table.add_row(
            h.name,
            h.hostname,
            h.user or "",
            str(h.port),
            h.source_file.name if h.source_file else "",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host")
@click.pass_context
def show(ctx: click.Context, host: str) -> None:
    """Show full configuration for a host."""
    mgr: SSHManager = ctx.obj["manager"]
    entry = mgr.get_host(host)

    if entry is None:
        err_console.print(f"Host not found: {host!r}")
        ctx.exit(1)

    lines = [
        f"[bold]Host:[/bold]         {entry.name}",
        f"[bold]HostName:[/bold]     {entry.hostname}",
        f"[bold]User:[/bold]         {entry.user or '[dim]—[/dim]'}",
        f"[bold]Port:[/bold]         {entry.port}",
        f"[bold]IdentityFile:[/bold] {entry.identity_file or '[dim]—[/dim]'}",
        f"[bold]ProxyJump:[/bold]    {entry.proxy_jump or '[dim]—[/dim]'}",
        f"[bold]ForwardAgent:[/bold] {entry.forward_agent if entry.forward_agent is not None else '[dim]—[/dim]'}",
    ]

    if entry.local_forwards:
        lines.append(f"[bold]LocalForward:[/bold] {', '.join(entry.local_forwards)}")

    if entry.extra_options:
        for k, v in entry.extra_options.items():
            lines.append(f"[bold]{k.capitalize()}:[/bold] {v}")

    source = entry.source_file.name if entry.source_file else "unknown"
    console.print(
        Panel("\n".join(lines), title=f"[bold]{entry.name}[/bold]", subtitle=source)
    )


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("name")
@click.option("--hostname", "-H", required=True, help="Server address or IP.")
@click.option("--user", "-u", default=None, help="SSH username.")
@click.option("--port", "-p", default=22, show_default=True, help="SSH port.")
@click.option("--identity-file", "-i", default=None, help="Path to private key.")
@click.option(
    "--config-file",
    "-c",
    default="sshaman-hosts",
    show_default=True,
    help="Target config.d filename.",
)
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    hostname: str,
    user: Optional[str],
    port: int,
    identity_file: Optional[str],
    config_file: str,
) -> None:
    """Add a new SSH host."""
    mgr: SSHManager = ctx.obj["manager"]
    entry = HostEntry(
        name=name,
        hostname=hostname,
        user=user,
        port=port,
        identity_file=Path(identity_file) if identity_file else None,
    )

    try:
        mgr.add_host(entry, config_file=config_file)
        console.print(
            f"[green]✓[/green] Added host [bold]{name}[/bold] to [dim]{config_file}[/dim]."
        )
    except DuplicateHostError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host")
@click.option("--hostname", "-H", default=None, help="New HostName.")
@click.option("--user", "-u", default=None, help="New username.")
@click.option("--port", "-p", default=None, type=int, help="New port.")
@click.option("--identity-file", "-i", default=None, help="New identity file path.")
@click.pass_context
def edit(
    ctx: click.Context,
    host: str,
    hostname: Optional[str],
    user: Optional[str],
    port: Optional[int],
    identity_file: Optional[str],
) -> None:
    """Edit an existing SSH host."""
    mgr: SSHManager = ctx.obj["manager"]
    updates: dict = {}
    if hostname is not None:
        updates["hostname"] = hostname
    if user is not None:
        updates["user"] = user
    if port is not None:
        updates["port"] = port
    if identity_file is not None:
        updates["identity_file"] = Path(identity_file)

    if not updates:
        console.print("[yellow]No changes specified.[/yellow]")
        return

    try:
        mgr.edit_host(host, **updates)
        console.print(f"[green]✓[/green] Updated [bold]{host}[/bold].")
    except HostNotFoundError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def remove(ctx: click.Context, host: str, yes: bool) -> None:
    """Remove an SSH host."""
    mgr: SSHManager = ctx.obj["manager"]

    if not yes:
        click.confirm(f"Remove host {host!r}?", abort=True)

    try:
        mgr.remove_host(host)
        console.print(f"[green]✓[/green] Removed [bold]{host}[/bold].")
    except HostNotFoundError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host")
@click.pass_context
def connect(ctx: click.Context, host: str) -> None:
    """Connect to a host via SSH."""
    mgr: SSHManager = ctx.obj["manager"]
    try:
        cmd = mgr.connect_command(host)
        os.execvp(cmd[0], cmd)  # pragma: no cover — replaces process
    except HostNotFoundError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


# ---------------------------------------------------------------------------
# sftp
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host")
@click.pass_context
def sftp(ctx: click.Context, host: str) -> None:
    """Connect to a host via SFTP."""
    mgr: SSHManager = ctx.obj["manager"]
    try:
        cmd = mgr.sftp_command(host)
        os.execvp(cmd[0], cmd)  # pragma: no cover — replaces process
    except HostNotFoundError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("pattern")
@click.pass_context
def search(ctx: click.Context, pattern: str) -> None:
    """Search hosts by name, hostname, or user."""
    ctx.invoke(list_hosts, pattern=pattern)


# ---------------------------------------------------------------------------
# config subgroup
# ---------------------------------------------------------------------------


@cli.group("config")
def config_group() -> None:
    """Manage SSH config files in config.d/."""


@config_group.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """List all config.d files."""
    mgr: SSHManager = ctx.obj["manager"]
    files = mgr.list_config_files()

    if not files:
        console.print("[dim]No config files found.[/dim]")
        return

    table = Table(title="config.d Files", show_header=True, header_style="bold cyan")
    table.add_column("Filename", style="bold")
    table.add_column("Hosts", justify="right")

    all_hosts = mgr.list_hosts()
    for path in files:
        count = sum(
            1 for h in all_hosts if h.source_file and h.source_file.name == path.name
        )
        table.add_row(path.name, str(count))

    console.print(table)


@config_group.command("create")
@click.argument("name")
@click.pass_context
def config_create(ctx: click.Context, name: str) -> None:
    """Create a new config.d file."""
    mgr: SSHManager = ctx.obj["manager"]
    try:
        path = mgr.create_config_file(name)
        console.print(f"[green]✓[/green] Created [bold]{path}[/bold].")
    except SSHConfigError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


@config_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@click.pass_context
def config_delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a config.d file."""
    mgr: SSHManager = ctx.obj["manager"]

    if not yes:
        click.confirm(f"Delete config file {name!r}?", abort=True)

    try:
        mgr.delete_config_file(name)
        console.print(f"[green]✓[/green] Deleted [bold]{name}[/bold].")
    except SSHConfigError as exc:
        err_console.print(str(exc))
        ctx.exit(1)


@config_group.command("show")
@click.argument("name")
@click.pass_context
def config_show(ctx: click.Context, name: str) -> None:
    """Show the raw contents of a config.d file."""
    mgr: SSHManager = ctx.obj["manager"]
    files = {f.name: f for f in mgr.list_config_files()}
    if name not in files:
        err_console.print(f"Config file not found: {name!r}")
        ctx.exit(1)
    content = files[name].read_text(encoding="utf-8")
    console.print(Panel(content, title=name))


@config_group.command("init")
@click.pass_context
def config_init(ctx: click.Context) -> None:
    """Initialise config.d/ and ensure ~/.ssh/config has the Include directive."""
    mgr: SSHManager = ctx.obj["manager"]
    mgr.ensure_setup()
    console.print("[green]✓[/green] SSH config.d setup is ready.")


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--source",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to legacy SSHaMan directory (default: ~/.config/sshaman).",
)
@click.option(
    "--config-file",
    default="sshaman-migrated",
    show_default=True,
    help="Target config.d filename.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be migrated without writing."
)
@click.option("--force", is_flag=True, help="Overwrite existing target config file.")
@click.pass_context
def migrate(
    ctx: click.Context,
    source: Optional[Path],
    config_file: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Migrate legacy JSON configs to native SSH config format."""
    from backend.migrate import migrate as do_migrate

    mgr: SSHManager = ctx.obj["manager"]

    try:
        result = do_migrate(
            source=source,
            config_manager=mgr._config,
            config_file=config_file,
            dry_run=dry_run,
            force=force,
        )
    except SSHConfigError as exc:
        err_console.print(str(exc))
        ctx.exit(1)

    status = "[yellow](dry run)[/yellow]" if dry_run else ""
    console.print(f"\nSSHaMan Migration {status}")
    console.print("=" * 40)

    if not result.migrated and not result.errors:
        console.print("[dim]Nothing to migrate.[/dim]")
        return

    for entry in result.migrated:
        warns = result.warnings.get(entry.name, [])
        icon = "[yellow]⚠[/yellow]" if warns else "[green]✓[/green]"
        console.print(f"  {icon} {entry.name} → Host {entry.name}")
        for w in warns:
            console.print(f"      [yellow]{w}[/yellow]")

    for path, err in result.errors.items():
        console.print(f"  [red]✗[/red] {path}: {err}")

    action = "Would write" if dry_run else "Wrote"
    console.print(
        f"\n{action} [bold]{len(result.migrated)}[/bold] host(s) to [dim]{config_file}[/dim]."
    )

    if dry_run:
        console.print("[dim]Run without --dry-run to apply.[/dim]")

    if result.source_cleanup_reminder:
        console.print(
            f"\n[yellow]⚠ Security reminder:[/yellow] {result.source_cleanup_reminder}"
        )


if __name__ == "__main__":  # pragma: no cover — entry point guard
    cli()
