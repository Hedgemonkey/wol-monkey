"""EnsureOnlineService — polls until a machine is online or times out."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.domain.ports import MachineRepository, WakeAttemptRepository  # noqa: TC001
from app.domain.probe import ProbeState
from app.domain.wake_attempt import AttemptStatus
from app.infra.state_probe import StateProbe

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_S = 5


class EnsureOnlineService:
    def __init__(
        self,
        machine_repo: MachineRepository,
        attempt_repo: WakeAttemptRepository,
        probe: StateProbe | None = None,
        poll_interval: float = _POLL_INTERVAL_S,
    ) -> None:
        self._machines = machine_repo
        self._attempts = attempt_repo
        self._probe = probe or StateProbe()
        self._poll_interval = poll_interval

    async def run(self, attempt_id: str) -> AttemptStatus:
        """Poll until online, timed out, or failed. Updates attempt record throughout.

        Returns the final AttemptStatus.
        """
        attempt = await self._attempts.get_by_id(attempt_id)
        if attempt is None:
            logger.error("ensure_online_attempt_not_found", attempt_id=attempt_id)
            return AttemptStatus.FAILED

        machine = await self._machines.get_by_id(attempt.machine_id)
        if machine is None:
            await self._attempts.update_status(
                attempt_id,
                AttemptStatus.FAILED.value,
                error="Machine not found",
                finished_at=datetime.now(UTC),
            )
            return AttemptStatus.FAILED

        await self._attempts.update_status(attempt_id, AttemptStatus.WAKING.value)

        deadline = attempt.started_at
        if deadline is None:
            deadline = datetime.now(UTC)
        # Make deadline timezone-aware if it isn't
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        timeout_s = attempt.poll_timeout_s
        host = machine.hostname or machine.ip_address

        logger.info(
            "ensure_online_polling",
            attempt_id=attempt_id,
            machine_id=machine.id,
            host=host,
            timeout_s=timeout_s,
        )

        while True:
            elapsed = (datetime.now(UTC) - deadline).total_seconds()
            if elapsed >= timeout_s:
                await self._attempts.update_status(
                    attempt_id,
                    AttemptStatus.TIMEOUT.value,
                    error=f"Machine did not come online within {timeout_s}s",
                    finished_at=datetime.now(UTC),
                )
                logger.warning("ensure_online_timeout", attempt_id=attempt_id, elapsed=elapsed)
                return AttemptStatus.TIMEOUT

            result = await self._probe.probe(
                machine.id,
                host,
                machine.ssh_port,
                ip_fallback=machine.ip_address if machine.hostname else None,
            )
            if result.derived_state == ProbeState.ONLINE:
                await self._attempts.update_status(
                    attempt_id,
                    AttemptStatus.ONLINE.value,
                    finished_at=datetime.now(UTC),
                )
                logger.info(
                    "ensure_online_success",
                    attempt_id=attempt_id,
                    elapsed=elapsed,
                )
                return AttemptStatus.ONLINE

            await asyncio.sleep(self._poll_interval)
