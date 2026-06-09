"""WakeStrategy port (ABC) and implementations.

All subprocess/socket operations are confined to this module (infra layer).
Never import this from domain or services — depend on the ABC only.
"""

from __future__ import annotations

import asyncio
import socket
from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger(__name__)

# Magic packet: 6x 0xFF followed by MAC address repeated 16 times
_MAGIC_PORT = 9
_MAGIC_BROADCAST = "255.255.255.255"


def _build_magic_packet(mac: str) -> bytes:
    """Build a Wake-on-LAN magic packet for the given MAC address."""
    mac_clean = mac.replace(":", "").replace("-", "").upper()
    if len(mac_clean) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    mac_bytes = bytes.fromhex(mac_clean)
    return b"\xff" * 6 + mac_bytes * 16


class WakeStrategyPort(ABC):
    """Abstract base for wake strategies. Implementations live in infra."""

    @abstractmethod
    async def wake(self, mac: str, interface: str | None, broadcast: str | None) -> None:
        """Send a WoL magic packet. Raises on hard failure."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier matching domain WakeStrategy enum value."""
        ...


class EtherwakeStrategy(WakeStrategyPort):
    """Send WoL via the `etherwake` binary (requires CAP_NET_RAW / root)."""

    @property
    def name(self) -> str:
        return "etherwake"

    async def wake(self, mac: str, interface: str | None, broadcast: str | None) -> None:
        cmd = ["etherwake"]
        if interface:
            cmd += ["-i", interface]
        cmd.append(mac)
        logger.info("etherwake_send", mac=mac, interface=interface)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error("etherwake_failed", mac=mac, returncode=proc.returncode, stderr=err)
            raise RuntimeError(f"etherwake failed (rc={proc.returncode}): {err}")
        logger.info("etherwake_ok", mac=mac)


class UdpBroadcastStrategy(WakeStrategyPort):
    """Send WoL via UDP broadcast (no root required, works across subnets with directed broadcast)."""

    @property
    def name(self) -> str:
        return "udp"

    async def wake(self, mac: str, interface: str | None, broadcast: str | None) -> None:
        target = broadcast or _MAGIC_BROADCAST
        packet = _build_magic_packet(mac)
        logger.info("udp_wol_send", mac=mac, target=target, port=_MAGIC_PORT)
        # Run blocking socket I/O in a thread pool to stay async-friendly
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_udp_packet, packet, target, _MAGIC_PORT)
        logger.info("udp_wol_ok", mac=mac, target=target)


def _send_udp_packet(packet: bytes, target: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (target, port))


def get_strategy(name: str) -> WakeStrategyPort:
    """Return a WakeStrategyPort implementation by strategy name."""
    strategies: dict[str, WakeStrategyPort] = {
        "etherwake": EtherwakeStrategy(),
        "udp": UdpBroadcastStrategy(),
    }
    if name not in strategies:
        raise ValueError(f"Unknown wake strategy: {name!r}. Choose from {list(strategies)}")
    return strategies[name]
