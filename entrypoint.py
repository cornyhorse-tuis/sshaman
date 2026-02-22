"""SSHaMan entry point — delegates entirely to the Click CLI group.

The CLI itself handles the no-subcommand case by launching the TUI.
"""

from cli.sshaman_cli import cli

if __name__ == "__main__":  # pragma: no cover — entry point guard
    cli()
