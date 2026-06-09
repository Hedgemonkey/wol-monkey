"""SQLAlchemy implementations of domain repository ports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

from app.domain.ports import (
    ApiTokenRecord,
    ApiTokenRepository,
    MachineRecord,
    MachineRepository,
    SessionRecord,
    SessionRepository,
    SettingsRepository,
    SetupStateRecord,
    SetupStateRepository,
    UserRecord,
    UserRepository,
    WakeAttemptRecord,
    WakeAttemptRepository,
)
from app.persistence.models import (
    ApiTokenModel,
    MachineModel,
    SessionModel,
    SettingModel,
    SetupStateModel,
    UserModel,
    WakeAttemptModel,
)


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _user_to_record(m: UserModel) -> UserRecord:
    return UserRecord(
        id=m.id,
        username=m.username,
        password_hash=m.password_hash,
        role=m.role,
        created_at=m.created_at,
        last_login_at=m.last_login_at,
    )


def _machine_to_record(m: MachineModel) -> MachineRecord:
    return MachineRecord(
        id=m.id,
        name=m.name,
        hostname=m.hostname,
        ip_address=str(m.ip_address),
        mac_address=str(m.mac_address),
        ssh_port=m.ssh_port,
        wake_interface=m.wake_interface,
        wake_strategy=m.wake_strategy,
        broadcast_address=str(m.broadcast_address) if m.broadcast_address else None,
        enabled=m.enabled,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _attempt_to_record(m: WakeAttemptModel) -> WakeAttemptRecord:
    return WakeAttemptRecord(
        id=m.id,
        machine_id=m.machine_id,
        actor_type=m.actor_type,
        actor_id=m.actor_id,
        strategy=m.strategy,
        status=m.status,
        ensure_online=m.ensure_online,
        poll_timeout_s=m.poll_timeout_s,
        error=m.error,
        started_at=m.started_at,
        finished_at=m.finished_at,
    )


def _session_to_record(m: SessionModel) -> SessionRecord:
    return SessionRecord(
        id=m.id,
        user_id=m.user_id,
        csrf_secret=m.csrf_secret,
        ip=str(m.ip) if m.ip else None,
        user_agent=m.user_agent,
        expires_at=m.expires_at,
        revoked=m.revoked,
        created_at=m.created_at,
    )


def _token_to_record(m: ApiTokenModel) -> ApiTokenRecord:
    return ApiTokenRecord(
        id=m.id,
        user_id=m.user_id,
        name=m.name,
        token_hash=m.token_hash,
        prefix=m.prefix,
        scopes=m.scopes,
        last_used_at=m.last_used_at,
        revoked_at=m.revoked_at,
        created_at=m.created_at,
    )


def _setup_to_record(m: SetupStateModel) -> SetupStateRecord:
    return SetupStateRecord(
        id=m.id,
        completed=m.completed,
        current_step=m.current_step,
        completed_steps=m.completed_steps,
        updated_at=m.updated_at,
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class SqlUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: str) -> UserRecord | None:
        if not _is_valid_uuid(user_id):
            return None
        result = await self._session.get(UserModel, user_id)
        return _user_to_record(result) if result else None

    async def get_by_username(self, username: str) -> UserRecord | None:
        stmt = select(UserModel).where(UserModel.username == username)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _user_to_record(row) if row else None

    async def create(self, username: str, password_hash: str, role: str = "admin") -> UserRecord:
        model = UserModel(username=username, password_hash=password_hash, role=role)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _user_to_record(model)

    async def update_last_login(self, user_id: str) -> None:
        stmt = (
            update(UserModel).where(UserModel.id == user_id).values(last_login_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        stmt = update(UserModel).where(UserModel.id == user_id).values(password_hash=password_hash)
        await self._session.execute(stmt)

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(UserModel))
        return result.scalar_one()


# ---------------------------------------------------------------------------
# Machine
# ---------------------------------------------------------------------------
class SqlMachineRepository(MachineRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, machine_id: str) -> MachineRecord | None:
        if not _is_valid_uuid(machine_id):
            return None
        result = await self._session.get(MachineModel, machine_id)
        return _machine_to_record(result) if result else None

    async def list_all(self, enabled_only: bool = False) -> list[MachineRecord]:
        stmt = select(MachineModel)
        if enabled_only:
            stmt = stmt.where(MachineModel.enabled.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_machine_to_record(r) for r in rows]

    async def create(self, **kwargs: object) -> MachineRecord:
        model = MachineModel(**kwargs)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _machine_to_record(model)

    async def update(self, machine_id: str, **kwargs: object) -> MachineRecord | None:
        if not _is_valid_uuid(machine_id):
            return None
        model = await self._session.get(MachineModel, machine_id)
        if model is None:
            return None
        for k, v in kwargs.items():
            setattr(model, k, v)
        await self._session.flush()
        await self._session.refresh(model)
        return _machine_to_record(model)

    async def delete(self, machine_id: str) -> bool:
        if not _is_valid_uuid(machine_id):
            return False
        model = await self._session.get(MachineModel, machine_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(MachineModel))
        return result.scalar_one()


# ---------------------------------------------------------------------------
# WakeAttempt
# ---------------------------------------------------------------------------
class SqlWakeAttemptRepository(WakeAttemptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs: object) -> WakeAttemptRecord:
        model = WakeAttemptModel(**kwargs)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _attempt_to_record(model)

    async def get_by_id(self, attempt_id: str) -> WakeAttemptRecord | None:
        if not _is_valid_uuid(attempt_id):
            return None
        result = await self._session.get(WakeAttemptModel, attempt_id)
        return _attempt_to_record(result) if result else None

    async def update_status(
        self,
        attempt_id: str,
        status: str,
        error: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if error is not None:
            values["error"] = error
        if finished_at is not None:
            values["finished_at"] = finished_at
        stmt = update(WakeAttemptModel).where(WakeAttemptModel.id == attempt_id).values(**values)
        await self._session.execute(stmt)

    async def list_for_machine(self, machine_id: str, limit: int = 20) -> list[WakeAttemptRecord]:
        stmt = (
            select(WakeAttemptModel)
            .where(WakeAttemptModel.machine_id == machine_id)
            .order_by(WakeAttemptModel.started_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_attempt_to_record(r) for r in rows]

    async def get_active_for_machine(self, machine_id: str) -> WakeAttemptRecord | None:
        stmt = (
            select(WakeAttemptModel)
            .where(
                WakeAttemptModel.machine_id == machine_id,
                WakeAttemptModel.status.in_(["pending", "sent", "waking"]),
            )
            .order_by(WakeAttemptModel.started_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _attempt_to_record(row) if row else None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class SqlSessionRepository(SessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: str,
        csrf_secret: str,
        expires_at: datetime,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionRecord:
        model = SessionModel(
            user_id=user_id,
            csrf_secret=csrf_secret,
            expires_at=expires_at,
            ip=ip,
            user_agent=user_agent,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _session_to_record(model)

    async def get_by_id(self, session_id: str) -> SessionRecord | None:
        if not _is_valid_uuid(session_id):
            return None
        result = await self._session.get(SessionModel, session_id)
        return _session_to_record(result) if result else None

    async def revoke(self, session_id: str) -> None:
        stmt = update(SessionModel).where(SessionModel.id == session_id).values(revoked=True)
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: str) -> None:
        stmt = update(SessionModel).where(SessionModel.user_id == user_id).values(revoked=True)
        await self._session.execute(stmt)

    async def delete_expired(self) -> int:
        from typing import cast

        stmt = sa_delete(SessionModel).where(SessionModel.expires_at < datetime.now(UTC))
        result = cast("CursorResult[tuple[()]]", await self._session.execute(stmt))
        return result.rowcount


# ---------------------------------------------------------------------------
# ApiToken
# ---------------------------------------------------------------------------
class SqlApiTokenRepository(ApiTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, name: str, token_hash: str, prefix: str, scopes: dict[str, object], user_id: str
    ) -> ApiTokenRecord:
        model = ApiTokenModel(
            name=name, token_hash=token_hash, prefix=prefix, scopes=scopes, user_id=user_id
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _token_to_record(model)

    async def get_by_hash(self, token_hash: str) -> ApiTokenRecord | None:
        stmt = select(ApiTokenModel).where(
            ApiTokenModel.token_hash == token_hash,
            ApiTokenModel.revoked_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _token_to_record(row) if row else None

    async def list_active(self) -> list[ApiTokenRecord]:
        stmt = select(ApiTokenModel).where(ApiTokenModel.revoked_at.is_(None))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_token_to_record(r) for r in rows]

    async def revoke(self, token_id: str) -> None:
        stmt = (
            update(ApiTokenModel)
            .where(ApiTokenModel.id == token_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)

    async def touch_last_used(self, token_id: str) -> None:
        stmt = (
            update(ApiTokenModel)
            .where(ApiTokenModel.id == token_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)


# ---------------------------------------------------------------------------
# SetupState
# ---------------------------------------------------------------------------
class SqlSetupStateRepository(SetupStateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> SetupStateRecord:
        model = await self._session.get(SetupStateModel, 1)
        if model is None:
            model = SetupStateModel()
            self._session.add(model)
            await self._session.flush()
            await self._session.refresh(model)
        return _setup_to_record(model)

    async def update(self, **kwargs: object) -> SetupStateRecord:
        model = await self._session.get(SetupStateModel, 1)
        if model is None:
            model = SetupStateModel(**kwargs)
            self._session.add(model)
        else:
            for k, v in kwargs.items():
                setattr(model, k, v)
        await self._session.flush()
        await self._session.refresh(model)
        return _setup_to_record(model)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SqlSettingsRepository(SettingsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> object | None:
        model = await self._session.get(SettingModel, key)
        if model is None:
            return None
        return model.value.get("v")

    async def set(self, key: str, value: object) -> None:
        model = await self._session.get(SettingModel, key)
        if model is None:
            model = SettingModel(key=key, value={"v": value})
            self._session.add(model)
        else:
            model.value = {"v": value}
        await self._session.flush()

    async def get_all(self) -> dict[str, object]:
        stmt = select(SettingModel)
        rows = (await self._session.execute(stmt)).scalars().all()
        return {r.key: r.value.get("v") for r in rows}
