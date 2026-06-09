"""Setup wizard API — first-run configuration endpoints.

All wizard steps are unauthenticated EXCEPT steps after admin creation.
The setup guard middleware (app/api/middleware.py) redirects non-wizard
requests to /setup when wizard is incomplete.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db_session
from app.persistence.repositories import (
    SqlApiTokenRepository,
    SqlSessionRepository,
    SqlSettingsRepository,
    SqlSetupStateRepository,
    SqlUserRepository,
)
from app.security.auth_service import get_auth_service
from app.services.auth import AuthenticationError
from app.services.settings import SettingsService
from app.services.setup_state import WIZARD_STEPS, SetupStateService

router = APIRouter(tags=["setup"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SetupStatusResponse(BaseModel):
    completed: bool
    current_step: str
    completed_steps: dict[str, object]
    steps: list[str]


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=12, max_length=1024)


class NetworkConfigRequest(BaseModel):
    wake_interface: str = Field(default="", max_length=32)
    default_wake_strategy: str = Field(default="etherwake", max_length=20)
    default_poll_timeout_s: int = Field(default=120, ge=10, le=600)


class WizardCompleteRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _require_incomplete(db: AsyncSession) -> None:
    svc = SetupStateService(SqlSetupStateRepository(db))
    if await svc.is_complete():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Setup already completed",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/setup/status",
    response_model=SetupStatusResponse,
    summary="Return current wizard state (unauthenticated)",
)
async def setup_status(db: DbSession) -> SetupStatusResponse:
    svc = SetupStateService(SqlSetupStateRepository(db))
    state = await svc.get_state()
    return SetupStatusResponse(
        completed=bool(state["completed"]),
        current_step=str(state["current_step"]),
        completed_steps=dict(state["completed_steps"])
        if isinstance(state["completed_steps"], dict)
        else {},
        steps=WIZARD_STEPS,
    )


@router.post(
    "/setup/admin",
    status_code=status.HTTP_201_CREATED,
    summary="Create the initial admin account (step: admin_account)",
)
async def setup_admin(body: AdminCreateRequest, db: DbSession) -> dict[str, str]:
    await _require_incomplete(db)
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    try:
        user = await auth_svc.create_admin(body.username, body.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("admin_account")
    return {"id": user.id, "username": user.username}


@router.post(
    "/setup/network",
    summary="Configure network/wake settings (step: network)",
)
async def setup_network(body: NetworkConfigRequest, db: DbSession) -> dict[str, str]:
    await _require_incomplete(db)
    settings_svc = SettingsService(SqlSettingsRepository(db))
    await settings_svc.set("wake_interface", body.wake_interface)
    await settings_svc.set("default_wake_strategy", body.default_wake_strategy)
    await settings_svc.set("default_poll_timeout_s", body.default_poll_timeout_s)

    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("network")
    return {"status": "ok"}


@router.post(
    "/setup/complete",
    summary="Mark wizard as complete",
)
async def setup_complete(db: DbSession) -> dict[str, str]:
    await _require_incomplete(db)
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("complete")
    return {"status": "setup_complete"}
