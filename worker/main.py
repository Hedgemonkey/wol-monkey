"""WoL-Monkey worker process.

Runs in a separate container with:
  - network_mode: host  (for L2 access via etherwake)
  - cap_add: [NET_RAW]  (for raw socket / etherwake)

Polls the wake_jobs table for queued jobs, executes them, updates status.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.persistence.repositories import (
    SqlMachineRepository,
    SqlWakeAttemptRepository,
)
from app.services.ensure_online import EnsureOnlineService
from app.services.wake import WakeService
from worker.job_queue import JobQueue

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_S = 2
_shutdown = False


def _handle_signal(signum: int, frame: object) -> None:
    global _shutdown
    logger.info("worker_shutdown_signal", signum=signum)
    _shutdown = True


async def _process_job(session: AsyncSession, job_id: str, payload: dict[str, object]) -> None:
    machine_repo = SqlMachineRepository(session)
    attempt_repo = SqlWakeAttemptRepository(session)

    machine_id = str(payload.get("machine_id", ""))
    attempt_id = str(payload.get("attempt_id", ""))
    ensure_online = bool(payload.get("ensure_online", False))
    poll_timeout_s = int(str(payload.get("poll_timeout_s", 120)))
    strategy_override: str | None = (
        str(payload["strategy_override"]) if payload.get("strategy_override") else None
    )
    actor_type = str(payload.get("actor_type", "system"))
    actor_id = str(payload.get("actor_id", "worker"))

    wake_svc = WakeService(machine_repo=machine_repo, attempt_repo=attempt_repo)
    try:
        await wake_svc.wake(
            machine_id=machine_id,
            actor_type=actor_type,
            actor_id=actor_id,
            ensure_online=ensure_online,
            poll_timeout_s=poll_timeout_s,
            strategy_override=strategy_override,
        )
    except Exception as exc:
        logger.error("job_wake_failed", job_id=job_id, error=str(exc))
        return

    if ensure_online:
        active = await attempt_repo.get_active_for_machine(machine_id)
        run_id = active.id if active is not None else attempt_id
        if run_id:
            eo_svc = EnsureOnlineService(
                machine_repo=machine_repo,
                attempt_repo=attempt_repo,
            )
            final_status = await eo_svc.run(run_id)
            logger.info("job_ensure_online_done", job_id=job_id, status=final_status.value)


async def run_worker() -> None:
    settings = get_settings()

    logging.basicConfig(level=settings.log_level.upper())
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
    )

    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    logger.info("worker_started", poll_interval=_POLL_INTERVAL_S)

    job_queue = JobQueue(factory)

    while not _shutdown:
        try:
            job = await job_queue.claim_next()
            if job is not None:
                job_id, payload = job
                logger.info("job_claimed", job_id=job_id)
                async with factory() as session:
                    try:
                        await _process_job(session, job_id, payload)
                        await job_queue.mark_done(job_id)
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        await job_queue.mark_error(job_id, str(exc))
                        logger.error("job_error", job_id=job_id, error=str(exc))
        except Exception as exc:
            logger.error("worker_loop_error", error=str(exc))

        await asyncio.sleep(_POLL_INTERVAL_S)

    await engine.dispose()
    logger.info("worker_stopped")


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
