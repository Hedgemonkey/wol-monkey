"""Unit tests for EnsureOnlineService — probe is fully mocked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.domain.probe import ProbeResult
from app.domain.wake_attempt import AttemptStatus
from app.services.ensure_online import EnsureOnlineService


def _make_attempt(
    timeout_s: int = 30,
    started_at: datetime | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = "attempt-1"
    a.machine_id = "machine-1"
    a.poll_timeout_s = timeout_s
    a.started_at = started_at or datetime.now(UTC)
    return a


def _make_machine() -> MagicMock:
    m = MagicMock()
    m.id = "machine-1"
    m.ip_address = "10.0.0.1"
    m.hostname = None
    m.ssh_port = 22
    return m


def _probe_result(machine_id: str, online: bool) -> ProbeResult:
    return ProbeResult(
        machine_id=machine_id,
        ping_ok=online,
        tcp_ssh_ok=online,
        observed_at=datetime.now(UTC),
    )


class TestEnsureOnlineService:
    def _make_service(
        self, probe: MagicMock | None = None
    ) -> tuple[EnsureOnlineService, AsyncMock, AsyncMock]:
        machine_repo = AsyncMock()
        attempt_repo = AsyncMock()
        mock_probe = probe or MagicMock()
        svc = EnsureOnlineService(
            machine_repo=machine_repo,
            attempt_repo=attempt_repo,
            probe=mock_probe,
            poll_interval=0.01,  # fast polling for tests
        )
        return svc, machine_repo, attempt_repo

    async def test_returns_failed_if_attempt_not_found(self) -> None:
        svc, _machine_repo, attempt_repo = self._make_service()
        attempt_repo.get_by_id.return_value = None
        result = await svc.run("bad-attempt")
        assert result == AttemptStatus.FAILED

    async def test_returns_failed_if_machine_not_found(self) -> None:
        svc, machine_repo, attempt_repo = self._make_service()
        attempt_repo.get_by_id.return_value = _make_attempt()
        machine_repo.get_by_id.return_value = None
        result = await svc.run("attempt-1")
        assert result == AttemptStatus.FAILED

    async def test_online_on_first_probe(self) -> None:
        probe = AsyncMock()
        probe.probe.return_value = _probe_result("machine-1", online=True)
        svc, machine_repo, attempt_repo = self._make_service(probe=probe)
        attempt_repo.get_by_id.return_value = _make_attempt()
        machine_repo.get_by_id.return_value = _make_machine()

        result = await svc.run("attempt-1")

        assert result == AttemptStatus.ONLINE
        # Confirm WAKING then ONLINE transitions were called
        calls = [c[0][1] for c in attempt_repo.update_status.call_args_list]
        assert AttemptStatus.WAKING.value in calls
        assert AttemptStatus.ONLINE.value in calls

    async def test_timeout_when_always_offline(self) -> None:
        probe = AsyncMock()
        probe.probe.return_value = _probe_result("machine-1", online=False)
        # Set started_at in the past beyond timeout
        old_start = datetime.now(UTC) - timedelta(seconds=200)
        svc, machine_repo, attempt_repo = self._make_service(probe=probe)
        attempt_repo.get_by_id.return_value = _make_attempt(timeout_s=10, started_at=old_start)
        machine_repo.get_by_id.return_value = _make_machine()

        result = await svc.run("attempt-1")

        assert result == AttemptStatus.TIMEOUT
        calls = [c[0][1] for c in attempt_repo.update_status.call_args_list]
        assert AttemptStatus.TIMEOUT.value in calls

    async def test_online_after_several_polls(self) -> None:
        probe = AsyncMock()
        # First two probes offline, third online
        probe.probe.side_effect = [
            _probe_result("machine-1", online=False),
            _probe_result("machine-1", online=False),
            _probe_result("machine-1", online=True),
        ]
        svc, machine_repo, attempt_repo = self._make_service(probe=probe)
        attempt_repo.get_by_id.return_value = _make_attempt(timeout_s=300)
        machine_repo.get_by_id.return_value = _make_machine()

        result = await svc.run("attempt-1")

        assert result == AttemptStatus.ONLINE
        assert probe.probe.call_count == 3
