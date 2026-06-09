"""System information endpoints (unauthenticated — read-only, no secrets)."""

from __future__ import annotations

import fcntl
import os
import re
import socket
import struct

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])

# IFF flags from linux/if.h
_IFF_UP = 0x1
_IFF_LOOPBACK = 0x8
_IFF_POINTTOPOINT = 0x10
_IFF_RUNNING = 0x40


def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _classify(name: str) -> str:
    """Return interface type label based on name and sysfs attributes."""
    if name.startswith("lo"):
        return "loopback"
    if name.startswith("veth"):
        return "veth"
    if name.startswith("docker") or name.startswith("br-"):
        return "docker-bridge"
    if name.startswith("hassio") or name.startswith("virbr"):
        return "bridge"
    wireless_path = f"/sys/class/net/{name}/wireless"
    if os.path.isdir(wireless_path):
        return "wifi"
    if os.path.isdir(f"/sys/class/net/{name}/bridge"):
        return "bridge"
    return "ethernet"


_SIOCGIFADDR = 0x8915


def _get_ip_addresses(name: str) -> list[str]:
    """Return the primary IPv4 address for an interface using ioctl."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ifreq = struct.pack("16sH14s", name.encode(), socket.AF_INET, b"\x00" * 14)
        res = fcntl.ioctl(s.fileno(), _SIOCGIFADDR, ifreq)
        s.close()
        ip = socket.inet_ntoa(res[20:24])
        if ip and ip != "0.0.0.0":
            return [ip]
    except OSError:
        pass
    return []


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class NetworkInterface(BaseModel):
    name: str
    type: str
    is_loopback: bool
    is_up: bool
    is_running: bool
    mac_address: str
    ip_addresses: list[str]


class DiscoveredHost(BaseModel):
    ip_address: str
    mac_address: str
    interface: str
    flags: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _list_interfaces() -> list[NetworkInterface]:
    """Read network interfaces from /sys/class/net (Linux)."""
    interfaces: list[NetworkInterface] = []
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return interfaces

    for name in names:
        base = f"/sys/class/net/{name}"
        flags_raw = _read(f"{base}/flags")
        try:
            flags = int(flags_raw, 16)
        except ValueError:
            flags = 0

        mac = _read(f"{base}/address")
        itype = _classify(name)
        ips = _get_ip_addresses(name)

        interfaces.append(
            NetworkInterface(
                name=name,
                type=itype,
                is_loopback=bool(flags & _IFF_LOOPBACK),
                is_up=bool(flags & _IFF_UP),
                is_running=bool(flags & _IFF_RUNNING),
                mac_address=mac,
                ip_addresses=ips,
            )
        )

    return interfaces


# /host/proc/net is mounted from host PID 1 in docker-compose (read-only).
# Fall back to /proc/net/arp for local development outside Docker.
_ARP_PATHS = ["/host/proc/net/arp", "/proc/net/arp"]


def _discover_hosts() -> list[DiscoveredHost]:
    """Parse the host kernel ARP table for known LAN hosts.

    Flags 0x2 = complete/reachable entry.
    Incomplete entries (all-zero MAC) are skipped.
    """
    hosts: list[DiscoveredHost] = []
    lines: list[str] = []
    for path in _ARP_PATHS:
        try:
            with open(path) as fh:
                lines = fh.readlines()[1:]  # skip header
            break
        except OSError:
            continue
    if not lines:
        return hosts

    for line in lines:
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 6:
            continue
        ip, _hwtype, flags, mac, _mask, iface = parts[:6]
        if mac == "00:00:00:00:00:00":
            continue
        hosts.append(
            DiscoveredHost(
                ip_address=ip,
                mac_address=mac.lower(),
                interface=iface,
                flags=flags,
            )
        )

    hosts.sort(key=lambda h: tuple(int(x) for x in h.ip_address.split(".")))
    return hosts


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/system/interfaces",
    response_model=list[NetworkInterface],
    summary="List host network interfaces with type, MAC and IP",
)
async def list_interfaces() -> list[NetworkInterface]:
    return _list_interfaces()


@router.get(
    "/system/discover",
    response_model=list[DiscoveredHost],
    summary="Return LAN hosts from kernel ARP cache (no scan required)",
)
async def discover_hosts() -> list[DiscoveredHost]:
    """Read the host kernel ARP table via /proc/net/arp.

    Returns hosts that have communicated with this machine recently.
    No network scan is performed — entries reflect the OS ARP cache.
    The target machine must be online and have been reached at least once
    (e.g. after a ping) to appear here.
    """
    return _discover_hosts()
