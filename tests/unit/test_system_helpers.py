"""Unit tests for system.py pure helper functions (no I/O required)."""

from __future__ import annotations

from unittest.mock import patch

from app.api.system import (
    NetworkInterface,
    _classify,
    _discover_hosts,
    _list_interfaces,
    _parse_dev_names,
    _parse_flags,
    _parse_iface_ips,
    _parse_wireless_names,
    _route_hex_to_be_int,
)

# ---------------------------------------------------------------------------
# _route_hex_to_be_int
# ---------------------------------------------------------------------------


class TestRouteHexToBeInt:
    def test_zero(self) -> None:
        assert _route_hex_to_be_int("00000000") == 0

    def test_known_value(self) -> None:
        # 0x0101A8C0 LE → 192.168.1.1 BE = 0xC0A80101
        result = _route_hex_to_be_int("0101A8C0")
        assert result == 0xC0A80101

    def test_returns_int(self) -> None:
        assert isinstance(_route_hex_to_be_int("0101A8C0"), int)


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_loopback_lo(self) -> None:
        assert _classify("lo", set()) == "loopback"

    def test_loopback_lo_alias(self) -> None:
        assert _classify("lo:0", set()) == "loopback"

    def test_veth(self) -> None:
        assert _classify("veth0abc", set()) == "veth"

    def test_docker_bridge(self) -> None:
        assert _classify("docker0", set()) == "docker-bridge"

    def test_br_prefix(self) -> None:
        assert _classify("br-abc123", set()) == "docker-bridge"

    def test_hassio_bridge(self) -> None:
        assert _classify("hassio", set()) == "bridge"

    def test_virbr_bridge(self) -> None:
        assert _classify("virbr0", set()) == "bridge"

    def test_wifi(self) -> None:
        assert _classify("wlan0", {"wlan0"}) == "wifi"

    def test_ethernet_default(self) -> None:
        assert _classify("eth0", set()) == "ethernet"

    def test_ethernet_enp(self) -> None:
        assert _classify("enp3s0", set()) == "ethernet"


# ---------------------------------------------------------------------------
# _parse_dev_names
# ---------------------------------------------------------------------------

_DEV_CONTENT = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:   12345       100    0    0    0     0          0         0    12345       100    0    0    0     0       0          0
  eth0:  999999      5000    0    0    0     0          0         0   999999      5000    0    0    0     0       0          0
 wlan0:       0         0    0    0    0     0          0         0        0         0    0    0    0     0       0          0
"""


class TestParseDevNames:
    def test_returns_interface_names(self) -> None:
        with patch("app.api.system._proc", return_value=_DEV_CONTENT):
            names = _parse_dev_names()
        assert "lo" in names
        assert "eth0" in names
        assert "wlan0" in names

    def test_skips_header_lines(self) -> None:
        with patch("app.api.system._proc", return_value=_DEV_CONTENT):
            names = _parse_dev_names()
        assert "Inter-" not in names
        assert "face" not in names

    def test_empty_proc_returns_empty(self) -> None:
        with patch("app.api.system._proc", return_value=""):
            assert _parse_dev_names() == []


# ---------------------------------------------------------------------------
# _parse_wireless_names
# ---------------------------------------------------------------------------

_WIRELESS_CONTENT = """\
Inter- | sta-  |   Quality        |   Discarded packets               | Missed | WE
 face  | tus   | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   70.  -40.  -256.        0      0      0      0      0        0
"""


class TestParseWirelessNames:
    def test_parses_wireless_iface(self) -> None:
        with patch("app.api.system._proc", return_value=_WIRELESS_CONTENT):
            names = _parse_wireless_names()
        assert "wlan0" in names

    def test_empty_returns_empty_set(self) -> None:
        with patch("app.api.system._proc", return_value=""):
            assert _parse_wireless_names() == set()


# ---------------------------------------------------------------------------
# _parse_flags
# ---------------------------------------------------------------------------

_ROUTE_CONTENT = """\
Iface   Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
eth0    0001A8C0    00000000 0001  0      0   0      00FFFFFF 0 0 0
"""


class TestParseFlags:
    def test_routed_iface_is_up(self) -> None:
        with patch(
            "app.api.system._proc",
            side_effect=lambda f: _ROUTE_CONTENT if f == "route" else _DEV_CONTENT,
        ):
            flags = _parse_flags()
        assert flags.get("eth0", 0) & 0x1  # up flag

    def test_lo_always_up(self) -> None:
        with patch(
            "app.api.system._proc",
            side_effect=lambda f: _ROUTE_CONTENT if f == "route" else _DEV_CONTENT,
        ):
            flags = _parse_flags()
        assert flags.get("lo", 0) & 0x1

    def test_lo_has_loopback_flag(self) -> None:
        with patch(
            "app.api.system._proc",
            side_effect=lambda f: _ROUTE_CONTENT if f == "route" else _DEV_CONTENT,
        ):
            flags = _parse_flags()
        assert flags.get("lo", 0) & 0x8

    def test_running_iface_has_flag(self) -> None:
        with patch(
            "app.api.system._proc",
            side_effect=lambda f: _ROUTE_CONTENT if f == "route" else _DEV_CONTENT,
        ):
            flags = _parse_flags()
        # eth0 has 5000 packets so should be running
        assert flags.get("eth0", 0) & 0x40


# ---------------------------------------------------------------------------
# _parse_iface_ips
# ---------------------------------------------------------------------------

_FIB_TRIE_CONTENT = """\
Main:
  +-- 0.0.0.0/0 3 0 5
     +-- 0.0.0.0/4 2 0 3
        |-- 0.0.0.0
           /0 universe UNICAST
     +-- 192.168.1.0/24 2 0 2
        |-- 192.168.1.0
           /24 link UNICAST
        +-- 192.168.1.0/28 2 0 2
           |-- 192.168.1.1
              /32 host LOCAL
           |-- 192.168.1.255
              /32 host LOCAL
"""

_ROUTE_FOR_IPS = """\
Iface   Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
eth0    0001A8C0    00000000 0003  0      0   100    00FFFFFF 0 0 0
"""


class TestParseIfaceIps:
    def test_assigns_ip_to_iface(self) -> None:
        def fake_proc(f: str) -> str:
            return _FIB_TRIE_CONTENT if f == "fib_trie" else _ROUTE_FOR_IPS

        with patch("app.api.system._proc", side_effect=fake_proc):
            result = _parse_iface_ips()
        assert "eth0" in result
        assert "192.168.1.1" in result["eth0"]

    def test_skips_broadcast_and_network(self) -> None:
        def fake_proc(f: str) -> str:
            return _FIB_TRIE_CONTENT if f == "fib_trie" else _ROUTE_FOR_IPS

        with patch("app.api.system._proc", side_effect=fake_proc):
            result = _parse_iface_ips()
        for ips in result.values():
            for ip in ips:
                assert not ip.endswith(".0")
                assert not ip.endswith(".255")

    def test_empty_proc_returns_empty(self) -> None:
        with patch("app.api.system._proc", return_value=""):
            assert _parse_iface_ips() == {}


# ---------------------------------------------------------------------------
# _discover_hosts
# ---------------------------------------------------------------------------

_ARP_CONTENT = """\
IP address       HW type     Flags       HW address            Mask     Device
192.168.1.100    0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0
192.168.1.101    0x1         0x0         11:22:33:44:55:66     *        eth0
192.168.1.200    0x1         0x2         00:00:00:00:00:00     *        eth0
"""


class TestDiscoverHosts:
    def test_parses_arp_entries(self) -> None:
        with patch("app.api.system._proc", return_value=_ARP_CONTENT):
            hosts = _discover_hosts()
        ips = [h.ip_address for h in hosts]
        assert "192.168.1.100" in ips
        assert "192.168.1.101" in ips

    def test_skips_zero_mac(self) -> None:
        with patch("app.api.system._proc", return_value=_ARP_CONTENT):
            hosts = _discover_hosts()
        macs = [h.mac_address for h in hosts]
        assert "00:00:00:00:00:00" not in macs

    def test_reachable_flag(self) -> None:
        with patch("app.api.system._proc", return_value=_ARP_CONTENT):
            hosts = _discover_hosts()
        reachable = {h.ip_address: h.is_reachable for h in hosts}
        assert reachable["192.168.1.100"] is True
        assert reachable["192.168.1.101"] is False

    def test_sorted_by_ip(self) -> None:
        with patch("app.api.system._proc", return_value=_ARP_CONTENT):
            hosts = _discover_hosts()
        ips = [h.ip_address for h in hosts]
        assert ips == sorted(ips, key=lambda ip: tuple(int(x) for x in ip.split(".")))

    def test_empty_arp_returns_empty(self) -> None:
        with patch("app.api.system._proc", return_value=""):
            assert _discover_hosts() == []


# ---------------------------------------------------------------------------
# _list_interfaces
# ---------------------------------------------------------------------------


class TestListInterfaces:
    def test_returns_network_interface_objects(self) -> None:
        with (
            patch("app.api.system._parse_wireless_names", return_value=set()),
            patch("app.api.system._parse_flags", return_value={"eth0": 0x41, "lo": 0x49}),
            patch("app.api.system._parse_iface_ips", return_value={"eth0": ["192.168.1.1"]}),
            patch("app.api.system._parse_dev_names", return_value=["lo", "eth0"]),
        ):
            result = _list_interfaces()
        assert len(result) == 2
        assert all(isinstance(i, NetworkInterface) for i in result)

    def test_loopback_classified_correctly(self) -> None:
        with (
            patch("app.api.system._parse_wireless_names", return_value=set()),
            patch("app.api.system._parse_flags", return_value={"lo": 0x49}),
            patch("app.api.system._parse_iface_ips", return_value={}),
            patch("app.api.system._parse_dev_names", return_value=["lo"]),
        ):
            result = _list_interfaces()
        lo = result[0]
        assert lo.type == "loopback"
        assert lo.is_loopback is True
        assert lo.is_virtual is True

    def test_virtual_flag_set_for_veth(self) -> None:
        with (
            patch("app.api.system._parse_wireless_names", return_value=set()),
            patch("app.api.system._parse_flags", return_value={}),
            patch("app.api.system._parse_iface_ips", return_value={}),
            patch("app.api.system._parse_dev_names", return_value=["veth0abc"]),
        ):
            result = _list_interfaces()
        assert result[0].is_virtual is True
