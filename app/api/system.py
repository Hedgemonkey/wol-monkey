"""System information endpoints — authentication required.

All data is read from /host/proc/net/* (bind-mounted from host PID 1's network
namespace in docker-compose) so it reflects the real host interfaces, not the
container's isolated namespace.  Falls back to /proc/net/* for local dev.
"""

from __future__ import annotations

import re
import socket
import struct

from fastapi import APIRouter
from pydantic import BaseModel

from app.security.dependencies import CurrentUser  # noqa: TC001

router = APIRouter(tags=["system"])

# Paths: prefer host-mounted namespace, fall back for local dev
_PROC_NET = "/host/proc/net"
_PROC_NET_FALLBACK = "/proc/net"


def _proc(filename: str) -> str:
    """Return the first readable path for a /proc/net file."""
    for base in (_PROC_NET, _PROC_NET_FALLBACK):
        path = f"{base}/{filename}"
        try:
            with open(path) as fh:
                return fh.read()
        except OSError:
            continue
    return ""


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
    is_reachable: bool
    is_wireless: bool


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_dev_names() -> list[str]:
    """Return interface names from /proc/net/dev (always present)."""
    names: list[str] = []
    for line in _proc("dev").splitlines()[2:]:  # skip 2-line header
        name = line.split(":")[0].strip()
        if name:
            names.append(name)
    return names


def _parse_wireless_names() -> set[str]:
    """Return set of wireless interface names from /proc/net/wireless."""
    names: set[str] = set()
    for line in _proc("wireless").splitlines()[2:]:  # skip 2-line header
        parts = line.split(":")
        if parts:
            names.add(parts[0].strip())
    return names


def _route_hex_to_be_int(h: str) -> int:
    """Route table stores IPs as LE hex; swap bytes to get BE int for inet_aton comparison."""
    return struct.unpack(">I", struct.pack("<I", int(h, 16)))[0]


def _parse_iface_ips() -> dict[str, list[str]]:
    """Return {iface: [ip, ...]} by parsing /proc/net/fib_trie for LOCAL /32 hosts.

    Walk fib_trie to find each /32 host LOCAL address, then correlate with
    the route table to assign addresses to interfaces.
    """
    # Step 1: collect all LOCAL /32 IPs from fib_trie
    local_ips: set[str] = set()
    content = _proc("fib_trie")
    lines = content.splitlines()
    prev_ip: str | None = None
    for line in lines:
        m = re.match(r"\s+\|--\s+(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            prev_ip = m.group(1)
            continue
        if prev_ip and "/32 host LOCAL" in line:
            local_ips.add(prev_ip)
            prev_ip = None
            continue
        prev_ip = None

    # Step 2: assign IPs to interfaces via route table
    # route table gives us iface -> network/mask; if LOCAL IP is in that subnet → assign
    iface_nets: list[tuple[str, int, int]] = []  # (iface, net_be, mask_be)
    for line in _proc("route").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        iface, dest_hex, _gw, flags_hex, _, _, _, mask_hex = parts[:8]
        try:
            flags = int(flags_hex, 16)
            if not (flags & 0x1):  # route must be up
                continue
            net_be = _route_hex_to_be_int(dest_hex)
            mask_be = _route_hex_to_be_int(mask_hex)
            iface_nets.append((iface, net_be, mask_be))
        except (ValueError, struct.error):
            continue

    # Most specific mask first — /32 before /24 before /16 before default /0
    iface_nets.sort(key=lambda t: bin(t[2]).count("1"), reverse=True)

    result: dict[str, list[str]] = {}
    for ip in local_ips:
        if ip.startswith("127.") or ip.endswith(".0") or ip.endswith(".255"):
            continue
        try:
            ip_be = struct.unpack(">I", socket.inet_aton(ip))[0]
        except OSError:
            continue
        for iface, net_be, mask_be in iface_nets:
            if (ip_be & mask_be) == (net_be & mask_be):
                result.setdefault(iface, []).append(ip)
                break

    return result


def _classify(name: str, wireless_names: set[str]) -> str:
    if name == "lo" or name.startswith("lo:"):
        return "loopback"
    if name.startswith("veth"):
        return "veth"
    if name.startswith("docker") or name.startswith("br-"):
        return "docker-bridge"
    if name.startswith("hassio") or name.startswith("virbr"):
        return "bridge"
    if name in wireless_names:
        return "wifi"
    return "ethernet"


def _parse_flags() -> dict[str, int]:
    """Read IFF flags from /proc/net/dev_snmp6 fallback via if_flags if available,
    otherwise derive up/running from traffic counters in /proc/net/dev."""
    # /proc/net/dev doesn't carry flags directly.
    # Use /sys/class/net/{name}/flags if accessible (may work on some mounts),
    # otherwise infer: interface is 'up' if it appears in the route table,
    # 'running' if it has non-zero rx OR tx packet counts.
    flags: dict[str, int] = {}

    # Collect ifaces that appear in route table (= configured/up)
    routed: set[str] = set()
    for line in _proc("route").splitlines()[1:]:
        parts = line.split()
        if parts:
            routed.add(parts[0])

    # Loopback is always up
    routed.add("lo")

    # Parse traffic counters from /proc/net/dev
    for line in _proc("dev").splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        parts = rest.split()
        if len(parts) < 9:
            continue
        rx_packets = int(parts[1])
        tx_packets = int(parts[9])
        is_up = name in routed
        is_running = rx_packets > 0 or tx_packets > 0
        flags[name] = (0x1 if is_up else 0) | (0x40 if is_running else 0) | (0x8 if name == "lo" else 0)

    return flags



# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def _list_interfaces() -> list[NetworkInterface]:
    wireless = _parse_wireless_names()
    flags_map = _parse_flags()
    ip_map = _parse_iface_ips()

    interfaces: list[NetworkInterface] = []
    for name in _parse_dev_names():
        flags = flags_map.get(name, 0)
        itype = _classify(name, wireless)
        interfaces.append(
            NetworkInterface(
                name=name,
                type=itype,
                is_loopback=bool(flags & 0x8),
                is_up=bool(flags & 0x1),
                is_running=bool(flags & 0x40),
                mac_address="",
                ip_addresses=ip_map.get(name, []),
            )
        )
    return interfaces


def _discover_hosts() -> list[DiscoveredHost]:
    """Parse the host kernel ARP table for known LAN hosts."""
    wireless = _parse_wireless_names()
    hosts: list[DiscoveredHost] = []

    for line in _proc("arp").splitlines()[1:]:
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
                is_reachable=flags == "0x2",
                is_wireless=iface in wireless,
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
    summary="List host network interfaces with type and IP",
)
async def list_interfaces(_user: CurrentUser) -> list[NetworkInterface]:
    return _list_interfaces()


@router.get(
    "/system/discover",
    response_model=list[DiscoveredHost],
    summary="Return LAN hosts from kernel ARP cache (no scan required)",
)
async def discover_hosts(_user: CurrentUser) -> list[DiscoveredHost]:
    """Read the host kernel ARP table.

    Returns hosts the machine has communicated with recently.
    No scan is performed — entries reflect the OS ARP cache only.
    A device must be online and reachable to appear here.
    """
    return _discover_hosts()
