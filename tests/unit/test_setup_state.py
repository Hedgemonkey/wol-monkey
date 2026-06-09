"""Unit tests for SetupStateService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.services.setup_state import WIZARD_STEPS, SetupStateService


def _make_record(
    completed: bool = False,
    current_step: str = "welcome",
    completed_steps: dict | None = None,
) -> MagicMock:
    r = MagicMock()
    r.completed = completed
    r.current_step = current_step
    r.completed_steps = completed_steps or {}
    return r


def _make_service(record: MagicMock) -> tuple[SetupStateService, AsyncMock]:
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=record)
    repo.update = AsyncMock()
    return SetupStateService(repo), repo


class TestGetState:
    async def test_returns_dict(self) -> None:
        svc, _ = _make_service(_make_record())
        state = await svc.get_state()
        assert set(state.keys()) == {"completed", "current_step", "completed_steps"}

    async def test_reflects_record(self) -> None:
        svc, _ = _make_service(_make_record(completed=True, current_step="complete"))
        state = await svc.get_state()
        assert state["completed"] is True
        assert state["current_step"] == "complete"


class TestIsComplete:
    async def test_false_when_not_done(self) -> None:
        svc, _ = _make_service(_make_record(completed=False))
        assert await svc.is_complete() is False

    async def test_true_when_done(self) -> None:
        svc, _ = _make_service(_make_record(completed=True))
        assert await svc.is_complete() is True


class TestAdvance:
    async def test_advance_welcome_moves_to_admin(self) -> None:
        svc, repo = _make_service(_make_record(current_step="welcome"))
        await svc.advance("welcome")
        repo.update.assert_awaited_once()
        _, kwargs = repo.update.call_args
        assert kwargs["current_step"] == "admin_account"
        assert kwargs["completed"] is False

    async def test_advance_marks_step_complete(self) -> None:
        svc, repo = _make_service(_make_record(current_step="welcome"))
        await svc.advance("welcome")
        _, kwargs = repo.update.call_args
        assert kwargs["completed_steps"]["welcome"] is True

    async def test_advance_final_step_sets_completed(self) -> None:
        svc, repo = _make_service(_make_record(current_step="complete"))
        await svc.advance(WIZARD_STEPS[-1])
        _, kwargs = repo.update.call_args
        assert kwargs["completed"] is True

    async def test_advance_unknown_step_keeps_same(self) -> None:
        svc, repo = _make_service(_make_record(current_step="welcome"))
        await svc.advance("nonexistent")
        _, kwargs = repo.update.call_args
        assert kwargs["current_step"] == "nonexistent"


class TestGoBack:
    async def test_go_back_from_second_step(self) -> None:
        svc, repo = _make_service(_make_record(current_step="admin_account"))
        result = await svc.go_back("admin_account")
        assert result == "welcome"
        repo.update.assert_awaited_once()

    async def test_go_back_from_first_step_stays(self) -> None:
        svc, repo = _make_service(_make_record(current_step="welcome"))
        result = await svc.go_back("welcome")
        assert result == "welcome"
        repo.update.assert_not_awaited()

    async def test_go_back_unknown_step_returns_same(self) -> None:
        svc, repo = _make_service(_make_record())
        result = await svc.go_back("nonexistent")
        assert result == "nonexistent"
        repo.update.assert_not_awaited()

    async def test_go_back_clears_steps(self) -> None:
        svc, repo = _make_service(
            _make_record(
                current_step="network",
                completed_steps={"welcome": True, "admin_account": True, "network": True},
            )
        )
        await svc.go_back("network")
        _, kwargs = repo.update.call_args
        assert "network" not in kwargs["completed_steps"]
        assert "admin_account" not in kwargs["completed_steps"]


class TestReset:
    async def test_reset_clears_all(self) -> None:
        svc, repo = _make_service(_make_record(completed=True, current_step="complete"))
        await svc.reset()
        repo.update.assert_awaited_once_with(
            completed=False,
            current_step=WIZARD_STEPS[0],
            completed_steps={},
        )
