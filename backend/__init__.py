"""SSHaMan backend — SSH config management."""

from backend.host_entry import HostEntry
from backend.ssh_config import SSHConfigManager
from backend.manager import SSHManager

__all__ = ["HostEntry", "SSHConfigManager", "SSHManager"]
