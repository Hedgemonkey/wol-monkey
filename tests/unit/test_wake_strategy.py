"""Unit tests for WakeStrategy infra implementations."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.infra.wake_strategy import (
    UdpBroadcastStrategy,
    _build_magic_packet,
    get_strategy,
)


class TestMagicPacket:
    def test_packet_length(self) -> None:
        pkt = _build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert len(pkt) == 6 + 6 * 16  # 6 FF bytes + 16 repetitions of 6-byte MAC

    def test_starts_with_six_ff(self) -> None:
        pkt = _build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert pkt[:6] == b"\xff" * 6

    def test_mac_repeated_16_times(self) -> None:
        mac = "aa:bb:cc:dd:ee:ff"
        pkt = _build_magic_packet(mac)
        mac_bytes = bytes.fromhex("aabbccddeeff")
        assert pkt[6:] == mac_bytes * 16

    def test_dashes_accepted(self) -> None:
        pkt = _build_magic_packet("aa-bb-cc-dd-ee-ff")
        assert len(pkt) == 102

    def test_invalid_mac_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC"):
            _build_magic_packet("not-a-mac")


class TestUdpBroadcastStrategy:
    async def test_sends_to_default_broadcast(self) -> None:
        strategy = UdpBroadcastStrategy()
        with patch("app.infra.wake_strategy._send_udp_packet"):
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
                await strategy.wake(mac="aa:bb:cc:dd:ee:ff", interface=None, broadcast=None)
            mock_loop.return_value.run_in_executor.assert_awaited_once()

    async def test_uses_custom_broadcast(self) -> None:
        strategy = UdpBroadcastStrategy()
        captured: list = []

        async def fake_executor(executor, fn, *args):
            captured.append(args)

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = fake_executor
            await strategy.wake(
                mac="aa:bb:cc:dd:ee:ff",
                interface=None,
                broadcast="192.168.1.255",
            )
        # The broadcast address should be passed to _send_udp_packet
        assert captured[0][1] == "192.168.1.255"

    def test_name_is_udp_broadcast(self) -> None:
        assert UdpBroadcastStrategy().name == "udp_broadcast"


class TestGetStrategy:
    def test_get_udp_broadcast(self) -> None:
        s = get_strategy("udp_broadcast")
        assert s.name == "udp_broadcast"

    def test_get_etherwake(self) -> None:
        s = get_strategy("etherwake")
        assert s.name == "etherwake"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown wake strategy"):
            get_strategy("fax")
