"""DB-backed job queue for the worker process.

Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent claiming.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: TC002

from app.persistence.models import WakeJobModel

logger = structlog.get_logger(__name__)


class JobQueue:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def claim_next(self) -> tuple[str, dict] | None:  # type: ignore[type-arg]
        """Claim the oldest queued job. Returns (job_id, payload) or None."""
        async with self._factory() as session:
            stmt = (
                select(WakeJobModel)
                .where(WakeJobModel.status == "queued")
                .order_by(WakeJobModel.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None

            row.status = "running"
            row.claimed_at = datetime.now(UTC)
            await session.commit()

            payload: dict[str, object] = dict(row.payload)
            return row.id, payload

    async def mark_done(self, job_id: str) -> None:
        async with self._factory() as session:
            await session.execute(
                update(WakeJobModel).where(WakeJobModel.id == job_id).values(status="done")
            )
            await session.commit()

    async def mark_error(self, job_id: str, error: str) -> None:
        async with self._factory() as session:
            await session.execute(
                update(WakeJobModel)
                .where(WakeJobModel.id == job_id)
                .values(status="error", payload={"error": error})
            )
            await session.commit()

    async def enqueue(
        self,
        machine_id: str,
        attempt_id: str,
        job_type: str,
        payload: dict,  # type: ignore[type-arg]
    ) -> str:
        """Add a new job to the queue. Returns job_id."""
        async with self._factory() as session:
            job = WakeJobModel(
                machine_id=machine_id,
                attempt_id=attempt_id,
                job_type=job_type,
                payload=payload,
                status="queued",
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info("job_enqueued", job_id=job.id, machine_id=machine_id, job_type=job_type)
            return job.id
