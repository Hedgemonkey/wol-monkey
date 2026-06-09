"""SettingsService — typed key/value application settings backed by the DB."""

from __future__ import annotations

import structlog

from app.domain.ports import SettingsRepository  # noqa: TC001

logger = structlog.get_logger(__name__)

# Known setting keys and their expected Python types
_KNOWN_SETTINGS: dict[str, type] = {
    "app_title": str,
    "wake_interface": str,
    "default_wake_strategy": str,
    "default_poll_timeout_s": int,
    "allow_api_tokens": bool,
    "session_lifetime_hours": int,
    "probe_interval_s": int,
    "log_level": str,
}


class SettingsService:
    def __init__(self, repo: SettingsRepository) -> None:
        self._repo = repo

    async def get(self, key: str, default: object = None) -> object:
        val = await self._repo.get(key)
        return val if val is not None else default

    async def get_str(self, key: str, default: str = "") -> str:
        val = await self.get(key, default)
        return str(val)

    async def get_int(self, key: str, default: int = 0) -> int:
        val = await self.get(key, default)
        try:
            return int(str(val))
        except (ValueError, TypeError):
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        val = await self.get(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    async def set(self, key: str, value: object) -> None:
        await self._repo.set(key, value)
        logger.info("setting_updated", key=key)

    async def get_all(self) -> dict[str, object]:
        """Return all settings as {key: value}."""
        return await self._repo.get_all()
