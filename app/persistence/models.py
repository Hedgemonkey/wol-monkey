"""SQLAlchemy ORM models for all WoL-Monkey tables.

These are persistence-layer representations only.
Domain entities live in app/domain/ and are independent of SQLAlchemy.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, MACADDR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["SessionModel"]] = relationship(back_populates="user")

    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)


# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------
class MachineModel(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    mac_address: Mapped[str] = mapped_column(MACADDR, nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    wake_interface: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wake_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="etherwake")
    broadcast_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    wake_attempts: Mapped[list["WakeAttemptModel"]] = relationship(back_populates="machine")
    probe_results: Mapped[list["ProbeResultModel"]] = relationship(back_populates="machine")

    __table_args__ = (
        UniqueConstraint("mac_address", name="uq_machines_mac_address"),
        CheckConstraint("ssh_port >= 1 AND ssh_port <= 65535", name="ck_machines_ssh_port"),
        CheckConstraint(
            "wake_strategy IN ('etherwake', 'udp')",
            name="ck_machines_wake_strategy",
        ),
    )


# ---------------------------------------------------------------------------
# Wake Attempts
# ---------------------------------------------------------------------------
class WakeAttemptModel(Base):
    __tablename__ = "wake_attempts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    ensure_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poll_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    machine: Mapped["MachineModel"] = relationship(back_populates="wake_attempts")
    job: Mapped["WakeJobModel | None"] = relationship(back_populates="attempt", uselist=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','sent','waking','online','failed','timeout')",
            name="ck_wake_attempts_status",
        ),
        Index("ix_wake_attempts_machine_started", "machine_id", "started_at"),
    )


# ---------------------------------------------------------------------------
# Wake Jobs (internal DB-backed queue)
# ---------------------------------------------------------------------------
class WakeJobModel(Base):
    __tablename__ = "wake_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("wake_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    job_type: Mapped[str] = mapped_column(String(20), nullable=False, default="wake")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    attempt: Mapped["WakeAttemptModel"] = relationship(back_populates="job")

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','error')",
            name="ck_wake_jobs_status",
        ),
        CheckConstraint(
            "job_type IN ('wake','ensure_online')",
            name="ck_wake_jobs_type",
        ),
        Index("ix_wake_jobs_status_created", "status", "created_at"),
    )


# ---------------------------------------------------------------------------
# Probe Results
# ---------------------------------------------------------------------------
class ProbeResultModel(Base):
    __tablename__ = "probe_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    ping_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tcp_ssh_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    derived_state: Mapped[str] = mapped_column(String(20), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    machine: Mapped["MachineModel"] = relationship(back_populates="probe_results")

    __table_args__ = (Index("ix_probe_results_machine_observed", "machine_id", "observed_at"),)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    csrf_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["UserModel"] = relationship(back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_expires", "user_id", "expires_at"),)


# ---------------------------------------------------------------------------
# API Tokens
# ---------------------------------------------------------------------------
class ApiTokenModel(Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("token_hash", name="uq_api_tokens_hash"),)


# ---------------------------------------------------------------------------
# Audit Events
# ---------------------------------------------------------------------------
class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(
        BigInteger().with_variant(BigInteger, "postgresql"),
        primary_key=True,
        autoincrement=True,
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    __table_args__ = (Index("ix_audit_events_created", "created_at"),)


# ---------------------------------------------------------------------------
# Settings (key/value store)
# ---------------------------------------------------------------------------
class SettingModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ---------------------------------------------------------------------------
# Setup State (singleton, id must always = 1)
# ---------------------------------------------------------------------------
class SetupStateModel(Base):
    __tablename__ = "setup_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_step: Mapped[str] = mapped_column(String(50), nullable=False, default="welcome")
    completed_steps: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (CheckConstraint("id = 1", name="ck_setup_state_singleton"),)
