"""Probe result domain value object — framework-free."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from enum import StrEnum


class ProbeState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProbeResult:
    machine_id: str
    ping_ok: bool
    tcp_ssh_ok: bool
    observed_at: datetime

    @property
    def derived_state(self) -> ProbeState:
        if self.ping_ok or self.tcp_ssh_ok:
            return ProbeState.ONLINE
        return ProbeState.OFFLINE
