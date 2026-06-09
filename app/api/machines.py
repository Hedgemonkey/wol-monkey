"""Machines CRUD API — create, list, get, update, delete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.machine import WakeStrategy
from app.persistence.database import get_db_session
from app.persistence.repositories import SqlMachineRepository
from app.security.dependencies import CsrfProtected, CurrentUser, SessionOrTokenUser  # noqa: TC001

router = APIRouter(tags=["machines"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MachineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=7, max_length=45)
    mac_address: str = Field(min_length=14, max_length=17)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    hostname: str | None = Field(default=None, max_length=253)
    wake_interface: str | None = Field(default=None, max_length=32)
    wake_strategy: WakeStrategy = WakeStrategy.ETHERWAKE
    broadcast_address: str | None = Field(default=None, max_length=45)
    enabled: bool = True


class MachineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, min_length=7, max_length=45)
    mac_address: str | None = Field(default=None, min_length=14, max_length=17)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    hostname: str | None = None
    wake_interface: str | None = None
    wake_strategy: WakeStrategy | None = None
    broadcast_address: str | None = None
    enabled: bool | None = None


class MachineResponse(BaseModel):
    id: str
    name: str
    ip_address: str
    mac_address: str
    ssh_port: int
    hostname: str | None
    wake_interface: str | None
    wake_strategy: str
    broadcast_address: str | None
    enabled: bool
    created_at: str
    updated_at: str


def _to_response(record) -> MachineResponse:  # type: ignore[no-untyped-def]
    return MachineResponse(
        id=record.id,
        name=record.name,
        ip_address=record.ip_address,
        mac_address=record.mac_address,
        ssh_port=record.ssh_port,
        hostname=record.hostname,
        wake_interface=record.wake_interface,
        wake_strategy=record.wake_strategy,
        broadcast_address=record.broadcast_address,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/machines",
    response_model=list[MachineResponse],
    summary="List all machines",
)
async def list_machines(
    _user: SessionOrTokenUser,
    db: DbSession,
    enabled_only: bool = False,
) -> list[MachineResponse]:
    repo = SqlMachineRepository(db)
    records = await repo.list_all(enabled_only=enabled_only)
    return [_to_response(r) for r in records]


@router.post(
    "/machines",
    response_model=MachineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new machine",
)
async def create_machine(
    body: MachineCreate,
    _user: CurrentUser,
    _csrf: CsrfProtected,
    db: DbSession,
) -> MachineResponse:
    repo = SqlMachineRepository(db)
    record = await repo.create(**body.model_dump())
    return _to_response(record)


@router.get(
    "/machines/{machine_id}",
    response_model=MachineResponse,
    summary="Get a machine by ID",
)
async def get_machine(
    machine_id: str,
    _user: SessionOrTokenUser,
    db: DbSession,
) -> MachineResponse:
    repo = SqlMachineRepository(db)
    record = await repo.get_by_id(machine_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    return _to_response(record)


@router.patch(
    "/machines/{machine_id}",
    response_model=MachineResponse,
    summary="Update a machine",
)
async def update_machine(
    machine_id: str,
    body: MachineUpdate,
    _user: CurrentUser,
    _csrf: CsrfProtected,
    db: DbSession,
) -> MachineResponse:
    repo = SqlMachineRepository(db)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        record = await repo.get_by_id(machine_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
        return _to_response(record)
    record = await repo.update(machine_id, **updates)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    return _to_response(record)


@router.delete(
    "/machines/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a machine",
)
async def delete_machine(
    machine_id: str,
    _user: CurrentUser,
    _csrf: CsrfProtected,
    db: DbSession,
) -> None:
    repo = SqlMachineRepository(db)
    deleted = await repo.delete(machine_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
