"""SSHaMan backend — SSH config management."""

from backend.host_entry import HostEntry
from backend.manager import SSHManager
from backend.ssh_config import SSHConfigManager

__all__ = ["HostEntry", "SSHConfigManager", "SSHManager"]
