"""Wake and machine-status API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.wake_attempt import AttemptStatus
from app.infra.state_probe import StateProbe
from app.persistence.database import get_db_session, get_session_factory
from app.persistence.repositories import (
    SqlMachineRepository,
    SqlWakeAttemptRepository,
)
from app.security.dependencies import ApiToken, CsrfProtected, CurrentUser  # noqa: TC001
from app.services.wake import WakeError, WakeService
from worker.job_queue import JobQueue

router = APIRouter(tags=["wake"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class WakeRequest(BaseModel):
    ensure_online: bool = False
    poll_timeout_s: int = Field(default=120, ge=10, le=600)
    strategy_override: str | None = None


class WakeResponse(BaseModel):
    attempt_id: str
    status: str
    message: str


class AttemptStatusResponse(BaseModel):
    id: str
    machine_id: str
    status: str
    strategy: str
    ensure_online: bool
    error: str | None
    started_at: str
    finished_at: str | None


class MachineStatusResponse(BaseModel):
    machine_id: str
    ping_ok: bool
    tcp_ssh_ok: bool
    state: str
    observed_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/machines/{machine_id}/wake",
    response_model=WakeResponse,
    summary="Send a Wake-on-LAN packet (queued via worker)",
)
async def wake_machine(
    machine_id: str,
    body: WakeRequest,
    _csrf: CsrfProtected,
    db: DbSession,
    user: CurrentUser,
) -> WakeResponse:
    """Enqueue a wake job. The worker process executes it with CAP_NET_RAW."""
    machine_repo = SqlMachineRepository(db)
    machine = await machine_repo.get_by_id(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    attempt_repo = SqlWakeAttemptRepository(db)
    # Create attempt record so we have an ID to return immediately
    attempt = await attempt_repo.create(
        machine_id=machine_id,
        actor_type="user",
        actor_id=user.id,
        strategy=body.strategy_override or machine.wake_strategy,
        ensure_online=body.ensure_online,
        poll_timeout_s=body.poll_timeout_s,
    )

    # Enqueue the job for the worker
    factory = get_session_factory()
    queue = JobQueue(factory)
    await queue.enqueue(
        machine_id=machine_id,
        attempt_id=attempt.id,
        job_type="wake",
        payload={
            "machine_id": machine_id,
            "attempt_id": attempt.id,
            "ensure_online": body.ensure_online,
            "poll_timeout_s": body.poll_timeout_s,
            "strategy_override": body.strategy_override,
            "actor_type": "user",
            "actor_id": user.id,
        },
    )

    return WakeResponse(
        attempt_id=attempt.id,
        status=AttemptStatus.PENDING.value,
        message="Wake job queued",
    )


@router.post(
    "/machines/{machine_id}/wake/direct",
    response_model=WakeResponse,
    summary="Send WoL packet directly (API token only — for privileged clients)",
)
async def wake_machine_direct(
    machine_id: str,
    body: WakeRequest,
    token: ApiToken,
    db: DbSession,
) -> WakeResponse:
    """Direct wake — bypasses the job queue. Requires a valid API token.

    The caller must have CAP_NET_RAW or use the UDP strategy.
    """
    machine_repo = SqlMachineRepository(db)
    attempt_repo = SqlWakeAttemptRepository(db)
    svc = WakeService(machine_repo=machine_repo, attempt_repo=attempt_repo)
    try:
        attempt_id = await svc.wake(
            machine_id=machine_id,
            actor_type="api_token",
            actor_id=token.id,
            ensure_online=body.ensure_online,
            poll_timeout_s=body.poll_timeout_s,
            strategy_override=body.strategy_override,
        )
    except WakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return WakeResponse(
        attempt_id=attempt_id,
        status=AttemptStatus.SENT.value,
        message="Wake packet sent",
    )


@router.get(
    "/machines/{machine_id}/attempts/{attempt_id}",
    response_model=AttemptStatusResponse,
    summary="Poll a wake attempt's status",
)
async def get_attempt_status(
    machine_id: str,
    attempt_id: str,
    _user: CurrentUser,
    db: DbSession,
) -> AttemptStatusResponse:
    repo = SqlWakeAttemptRepository(db)
    attempt = await repo.get_by_id(attempt_id)
    if attempt is None or attempt.machine_id != machine_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return AttemptStatusResponse(
        id=attempt.id,
        machine_id=attempt.machine_id,
        status=attempt.status,
        strategy=attempt.strategy,
        ensure_online=attempt.ensure_online,
        error=attempt.error,
        started_at=attempt.started_at.isoformat(),
        finished_at=attempt.finished_at.isoformat() if attempt.finished_at else None,
    )


@router.get(
    "/machines/{machine_id}/status",
    response_model=MachineStatusResponse,
    summary="Live probe of machine online status",
)
async def machine_status(
    machine_id: str,
    _user: CurrentUser,
    db: DbSession,
) -> MachineStatusResponse:
    repo = SqlMachineRepository(db)
    machine = await repo.get_by_id(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    probe = StateProbe()
    result = await probe.probe(
        machine_id=machine_id,
        host=machine.hostname or machine.ip_address,
        ssh_port=machine.ssh_port,
    )
    return MachineStatusResponse(
        machine_id=machine_id,
        ping_ok=result.ping_ok,
        tcp_ssh_ok=result.tcp_ssh_ok,
        state=result.derived_state.value,
        observed_at=result.observed_at.isoformat(),
    )
