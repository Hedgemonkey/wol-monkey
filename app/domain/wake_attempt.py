"""WakeAttempt domain entity and status state machine — framework-free."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from enum import StrEnum


class AttemptStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    WAKING = "waking"
    ONLINE = "online"
    FAILED = "failed"
    TIMEOUT = "timeout"

    # Valid transitions from each state
    _TRANSITIONS: dict[str, set[str]]

    def __new__(cls, value: str) -> AttemptStatus:
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj

    def can_transition_to(self, next_status: AttemptStatus) -> bool:
        transitions: dict[str, set[str]] = {
            "pending": {"sent", "failed"},
            "sent": {"waking", "online", "failed", "timeout"},
            "waking": {"online", "failed", "timeout"},
            "online": set(),
            "failed": set(),
            "timeout": set(),
        }
        return next_status.value in transitions.get(self.value, set())

    @property
    def is_terminal(self) -> bool:
        return self in (AttemptStatus.ONLINE, AttemptStatus.FAILED, AttemptStatus.TIMEOUT)


@dataclass
class WakeAttempt:
    id: str
    machine_id: str
    actor_type: str
    actor_id: str
    strategy: str
    status: AttemptStatus
    ensure_online: bool = False
    poll_timeout_s: int = 120
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
