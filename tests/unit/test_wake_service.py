"""Unit tests for WakeService — all I/O is mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.wake_attempt import AttemptStatus
from app.services.wake import WakeError, WakeService


def _make_machine(enabled: bool = True, strategy: str = "udp") -> MagicMock:
    m = MagicMock()
    m.id = "machine-1"
    m.enabled = enabled
    m.mac_address = "aa:bb:cc:dd:ee:ff"
    m.wake_interface = None
    m.broadcast_address = None
    m.wake_strategy = strategy
    return m


def _make_attempt(attempt_id: str = "attempt-1") -> MagicMock:
    a = MagicMock()
    a.id = attempt_id
    a.status = AttemptStatus.PENDING.value
    return a


def _make_service() -> tuple[WakeService, AsyncMock, AsyncMock]:
    machine_repo = AsyncMock()
    attempt_repo = AsyncMock()
    svc = WakeService(machine_repo=machine_repo, attempt_repo=attempt_repo)
    return svc, machine_repo, attempt_repo


class TestWakeService:
    async def test_raises_if_machine_not_found(self) -> None:
        svc, machine_repo, _ = _make_service()
        machine_repo.get_by_id.return_value = None
        with pytest.raises(WakeError, match="not found"):
            await svc.wake("bad-id", "user", "uid")

    async def test_raises_if_machine_disabled(self) -> None:
        svc, machine_repo, _ = _make_service()
        machine_repo.get_by_id.return_value = _make_machine(enabled=False)
        with pytest.raises(WakeError, match="disabled"):
            await svc.wake("m1", "user", "uid")

    async def test_creates_attempt_and_sends(self) -> None:
        svc, machine_repo, attempt_repo = _make_service()
        machine_repo.get_by_id.return_value = _make_machine()
        attempt_repo.create.return_value = _make_attempt()

        with patch("app.services.wake.get_strategy") as mock_get:
            mock_strategy = AsyncMock()
            mock_get.return_value = mock_strategy
            result = await svc.wake("machine-1", "user", "uid")

        assert result == "attempt-1"
        mock_strategy.wake.assert_awaited_once()
        attempt_repo.update_status.assert_awaited_once_with("attempt-1", AttemptStatus.SENT.value)

    async def test_marks_failed_on_strategy_error(self) -> None:
        svc, machine_repo, attempt_repo = _make_service()
        machine_repo.get_by_id.return_value = _make_machine()
        attempt_repo.create.return_value = _make_attempt()

        with patch("app.services.wake.get_strategy") as mock_get:
            mock_strategy = AsyncMock()
            mock_strategy.wake.side_effect = RuntimeError("network error")
            mock_get.return_value = mock_strategy
            with pytest.raises(WakeError, match="network error"):
                await svc.wake("machine-1", "user", "uid")

        call_args = attempt_repo.update_status.call_args
        assert call_args[0][1] == AttemptStatus.FAILED.value

    async def test_strategy_override_used(self) -> None:
        svc, machine_repo, attempt_repo = _make_service()
        machine_repo.get_by_id.return_value = _make_machine(strategy="etherwake")
        attempt_repo.create.return_value = _make_attempt()

        with patch("app.services.wake.get_strategy") as mock_get:
            mock_strategy = AsyncMock()
            mock_get.return_value = mock_strategy
            await svc.wake("machine-1", "user", "uid", strategy_override="udp")

        mock_get.assert_called_once_with("udp")
