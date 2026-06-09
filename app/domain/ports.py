"""Repository port interfaces (abstract base classes).

Services depend on these interfaces only; persistence layer implements them.
This keeps the domain and service layers free of SQLAlchemy imports.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# Lightweight data transfer objects (not full domain entities yet)
# Used in Phase 1 to bridge ports without full domain model.
# Full domain entities added in Phase 3.
# ---------------------------------------------------------------------------


@dataclass
class UserRecord:
    id: str
    username: str
    password_hash: str
    role: str
    created_at: datetime
    last_login_at: datetime | None


@dataclass
class MachineRecord:
    id: str
    name: str
    hostname: str | None
    ip_address: str
    mac_address: str
    ssh_port: int
    wake_interface: str | None
    wake_strategy: str
    broadcast_address: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class WakeAttemptRecord:
    id: str
    machine_id: str
    actor_type: str
    actor_id: str
    strategy: str
    status: str
    ensure_online: bool
    poll_timeout_s: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass
class SessionRecord:
    id: str
    user_id: str
    csrf_secret: str
    ip: str | None
    user_agent: str | None
    expires_at: datetime
    revoked: bool
    created_at: datetime


@dataclass
class ApiTokenRecord:
    id: str
    user_id: str
    name: str
    token_hash: str
    prefix: str
    scopes: dict[str, object]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


@dataclass
class SetupStateRecord:
    id: int
    completed: bool
    current_step: str
    completed_steps: dict[str, object]
    updated_at: datetime


# ---------------------------------------------------------------------------
# Repository interfaces
# ---------------------------------------------------------------------------


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> UserRecord | None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> UserRecord | None: ...

    @abstractmethod
    async def create(
        self, username: str, password_hash: str, role: str = "admin"
    ) -> UserRecord: ...

    @abstractmethod
    async def update_last_login(self, user_id: str) -> None: ...

    @abstractmethod
    async def update_password_hash(self, user_id: str, password_hash: str) -> None: ...

    @abstractmethod
    async def count(self) -> int: ...


class MachineRepository(ABC):
    @abstractmethod
    async def get_by_id(self, machine_id: str) -> MachineRecord | None: ...

    @abstractmethod
    async def list_all(self, enabled_only: bool = False) -> list[MachineRecord]: ...

    @abstractmethod
    async def create(self, **kwargs: object) -> MachineRecord: ...

    @abstractmethod
    async def update(self, machine_id: str, **kwargs: object) -> MachineRecord | None: ...

    @abstractmethod
    async def delete(self, machine_id: str) -> bool: ...

    @abstractmethod
    async def count(self) -> int: ...


class WakeAttemptRepository(ABC):
    @abstractmethod
    async def create(self, **kwargs: object) -> WakeAttemptRecord: ...

    @abstractmethod
    async def get_by_id(self, attempt_id: str) -> WakeAttemptRecord | None: ...

    @abstractmethod
    async def update_status(
        self,
        attempt_id: str,
        status: str,
        error: str | None = None,
        finished_at: datetime | None = None,
    ) -> None: ...

    @abstractmethod
    async def list_for_machine(
        self, machine_id: str, limit: int = 20
    ) -> list[WakeAttemptRecord]: ...

    @abstractmethod
    async def get_active_for_machine(self, machine_id: str) -> WakeAttemptRecord | None: ...


class SessionRepository(ABC):
    @abstractmethod
    async def create(
        self,
        user_id: str,
        csrf_secret: str,
        expires_at: datetime,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionRecord: ...

    @abstractmethod
    async def get_by_id(self, session_id: str) -> SessionRecord | None: ...

    @abstractmethod
    async def revoke(self, session_id: str) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: str) -> None: ...

    @abstractmethod
    async def delete_expired(self) -> int: ...


class ApiTokenRepository(ABC):
    @abstractmethod
    async def create(
        self, name: str, token_hash: str, prefix: str, scopes: dict[str, object], user_id: str
    ) -> ApiTokenRecord: ...

    @abstractmethod
    async def get_by_hash(self, token_hash: str) -> ApiTokenRecord | None: ...

    @abstractmethod
    async def list_active(self) -> list[ApiTokenRecord]: ...

    @abstractmethod
    async def revoke(self, token_id: str) -> None: ...

    @abstractmethod
    async def touch_last_used(self, token_id: str) -> None: ...


class SetupStateRepository(ABC):
    @abstractmethod
    async def get(self) -> SetupStateRecord: ...

    @abstractmethod
    async def update(self, **kwargs: object) -> SetupStateRecord: ...


class SettingsRepository(ABC):
    @abstractmethod
    async def get(self, key: str) -> object | None: ...

    @abstractmethod
    async def set(self, key: str, value: object) -> None: ...

    @abstractmethod
    async def get_all(self) -> dict[str, object]: ...
