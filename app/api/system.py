"""System information endpoints (unauthenticated — read-only, no secrets)."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class NetworkInterface(BaseModel):
    name: str
    is_loopback: bool
    is_up: bool


def _list_interfaces() -> list[NetworkInterface]:
    """Read network interfaces from /sys/class/net (Linux) with fallback."""
    interfaces: list[NetworkInterface] = []
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return interfaces

    for name in names:
        base = f"/sys/class/net/{name}"
        try:
            with open(f"{base}/flags") as fh:
                flags_raw = fh.read().strip()
            flags = int(flags_raw, 16)
        except OSError:
            flags = 0

        is_loopback = bool(flags & 0x8)
        is_up = bool(flags & 0x1)

        interfaces.append(NetworkInterface(name=name, is_loopback=is_loopback, is_up=is_up))

    return interfaces


@router.get(
    "/system/interfaces",
    response_model=list[NetworkInterface],
    summary="List host network interfaces",
)
async def list_interfaces() -> list[NetworkInterface]:
    """Return network interfaces visible to the app container.

    Used by the setup wizard and settings page to populate the wake
    interface dropdown instead of requiring manual text entry.
    """
    return _list_interfaces()
