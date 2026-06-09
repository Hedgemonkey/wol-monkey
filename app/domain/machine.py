"""Machine domain entity — framework-free."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WakeStrategy(StrEnum):
    ETHERWAKE = "etherwake"
    UDP_BROADCAST = "udp_broadcast"


class MachineState(StrEnum):
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    WAKING = "waking"
    ONLINE = "online"


@dataclass
class Machine:
    id: str
    name: str
    ip_address: str
    mac_address: str
    ssh_port: int = 22
    hostname: str | None = None
    wake_interface: str | None = None
    wake_strategy: WakeStrategy = WakeStrategy.ETHERWAKE
    broadcast_address: str | None = None
    enabled: bool = True

    def wake_target(self) -> str:
        """Return the MAC address normalised for wake commands."""
        return self.mac_address

    def probe_host(self) -> str:
        """Preferred host to probe — hostname if set, else IP."""
        return self.hostname or self.ip_address
