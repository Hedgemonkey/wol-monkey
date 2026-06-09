"""WakeService — orchestrates sending a WoL packet and recording the attempt."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.domain.ports import MachineRepository, WakeAttemptRepository  # noqa: TC001
from app.domain.wake_attempt import AttemptStatus
from app.infra.wake_strategy import WakeStrategyPort, get_strategy

logger = structlog.get_logger(__name__)


class WakeError(Exception):
    pass


class WakeService:
    def __init__(
        self,
        machine_repo: MachineRepository,
        attempt_repo: WakeAttemptRepository,
    ) -> None:
        self._machines = machine_repo
        self._attempts = attempt_repo

    async def wake(
        self,
        machine_id: str,
        actor_type: str,
        actor_id: str,
        ensure_online: bool = False,
        poll_timeout_s: int = 120,
        strategy_override: str | None = None,
    ) -> str:
        """Send WoL packet, record attempt, return attempt_id."""
        machine = await self._machines.get_by_id(machine_id)
        if machine is None:
            raise WakeError(f"Machine {machine_id!r} not found")
        if not machine.enabled:
            raise WakeError(f"Machine {machine_id!r} is disabled")

        strategy_name = strategy_override or machine.wake_strategy
        attempt = await self._attempts.create(
            machine_id=machine_id,
            actor_type=actor_type,
            actor_id=actor_id,
            strategy=strategy_name,
            ensure_online=ensure_online,
            poll_timeout_s=poll_timeout_s,
        )
        logger.info(
            "wake_attempt_created",
            attempt_id=attempt.id,
            machine_id=machine_id,
            strategy=strategy_name,
        )

        strategy: WakeStrategyPort = get_strategy(strategy_name)
        try:
            await strategy.wake(
                mac=machine.mac_address,
                interface=machine.wake_interface,
                broadcast=machine.broadcast_address,
            )
            await self._attempts.update_status(attempt.id, AttemptStatus.SENT.value)
            logger.info("wake_packet_sent", attempt_id=attempt.id, machine_id=machine_id)
        except Exception as exc:
            error_msg = str(exc)
            await self._attempts.update_status(
                attempt.id,
                AttemptStatus.FAILED.value,
                error=error_msg,
                finished_at=datetime.now(UTC),
            )
            logger.error(
                "wake_packet_failed",
                attempt_id=attempt.id,
                machine_id=machine_id,
                error=error_msg,
            )
            raise WakeError(f"Wake failed: {error_msg}") from exc

        return attempt.id
