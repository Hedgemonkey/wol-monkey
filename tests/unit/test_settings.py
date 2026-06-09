"""Unit tests for SettingsService and SetupStateService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.services.settings import SettingsService
from app.services.setup_state import WIZARD_STEPS, SetupStateService


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------
class TestSettingsService:
    def _make(self) -> tuple[SettingsService, AsyncMock]:
        repo = AsyncMock()
        return SettingsService(repo), repo

    async def test_get_returns_default_when_missing(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = None
        result = await svc.get("missing_key", default="fallback")
        assert result == "fallback"

    async def test_get_returns_value_when_present(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = "stored_value"
        result = await svc.get("key")
        assert result == "stored_value"

    async def test_get_str_casts_to_string(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = 42
        result = await svc.get_str("key")
        assert result == "42"

    async def test_get_int_parses_correctly(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = "120"
        result = await svc.get_int("key")
        assert result == 120

    async def test_get_int_returns_default_on_bad_value(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = "not-a-number"
        result = await svc.get_int("key", default=99)
        assert result == 99

    async def test_get_bool_true(self) -> None:
        svc, repo = self._make()
        for truthy in ("true", "1", "yes", "True"):
            repo.get.return_value = truthy
            assert await svc.get_bool("key") is True

    async def test_get_bool_false(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = "false"
        assert await svc.get_bool("key") is False

    async def test_get_bool_native_bool(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = True
        assert await svc.get_bool("key") is True

    async def test_set_calls_repo(self) -> None:
        svc, repo = self._make()
        await svc.set("my_key", "my_value")
        repo.set.assert_awaited_once_with("my_key", "my_value")

    async def test_get_all_delegates(self) -> None:
        svc, repo = self._make()
        repo.get_all.return_value = {"a": 1, "b": 2}
        result = await svc.get_all()
        assert result == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# SetupStateService
# ---------------------------------------------------------------------------
class TestSetupStateService:
    def _make_record(
        self,
        completed: bool = False,
        current_step: str = "welcome",
        completed_steps: dict | None = None,
    ) -> MagicMock:
        r = MagicMock()
        r.completed = completed
        r.current_step = current_step
        r.completed_steps = completed_steps or {}
        return r

    def _make(self) -> tuple[SetupStateService, AsyncMock]:
        repo = AsyncMock()
        return SetupStateService(repo), repo

    async def test_is_complete_false(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = self._make_record(completed=False)
        assert await svc.is_complete() is False

    async def test_is_complete_true(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = self._make_record(completed=True)
        assert await svc.is_complete() is True

    async def test_get_state_returns_dict(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = self._make_record(current_step="network")
        state = await svc.get_state()
        assert state["current_step"] == "network"
        assert state["completed"] is False

    async def test_advance_moves_to_next_step(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = self._make_record(current_step="welcome")
        repo.update.return_value = self._make_record(current_step="admin_account")

        await svc.advance("welcome")

        call_kwargs = repo.update.call_args[1]
        assert call_kwargs["current_step"] == "admin_account"
        assert "welcome" in call_kwargs["completed_steps"]

    async def test_advance_complete_step_marks_completed(self) -> None:
        svc, repo = self._make()
        repo.get.return_value = self._make_record(
            current_step="complete",
            completed_steps={
                "welcome": True,
                "admin_account": True,
                "network": True,
                "first_machine": True,
            },
        )
        repo.update.return_value = self._make_record(completed=True)

        await svc.advance("complete")

        call_kwargs = repo.update.call_args[1]
        assert call_kwargs["completed"] is True

    async def test_wizard_steps_order(self) -> None:
        assert WIZARD_STEPS[0] == "welcome"
        assert WIZARD_STEPS[-1] == "complete"
        assert "admin_account" in WIZARD_STEPS
        assert "network" in WIZARD_STEPS

    async def test_reset_clears_state(self) -> None:
        svc, repo = self._make()
        repo.update.return_value = self._make_record()
        await svc.reset()
        call_kwargs = repo.update.call_args[1]
        assert call_kwargs["completed"] is False
        assert call_kwargs["completed_steps"] == {}
        assert call_kwargs["current_step"] == WIZARD_STEPS[0]
