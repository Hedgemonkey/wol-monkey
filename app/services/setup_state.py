"""SetupStateService — tracks the first-run wizard progress."""

from __future__ import annotations

import structlog

from app.domain.ports import SetupStateRepository  # noqa: TC001

logger = structlog.get_logger(__name__)

WIZARD_STEPS = ["welcome", "admin_account", "network", "first_machine", "complete"]


class SetupStateService:
    def __init__(self, repo: SetupStateRepository) -> None:
        self._repo = repo

    async def get_state(self) -> dict[str, object]:
        record = await self._repo.get()
        return {
            "completed": record.completed,
            "current_step": record.current_step,
            "completed_steps": record.completed_steps,
        }

    async def is_complete(self) -> bool:
        record = await self._repo.get()
        return record.completed

    async def advance(self, step: str) -> None:
        """Mark a wizard step as done and advance to the next."""
        record = await self._repo.get()
        completed_steps: dict[str, object] = dict(record.completed_steps)
        completed_steps[step] = True

        if step == WIZARD_STEPS[-1]:
            await self._repo.update(
                completed=True,
                current_step=step,
                completed_steps=completed_steps,
            )
            logger.info("wizard_completed")
            return

        # Find the next step
        try:
            idx = WIZARD_STEPS.index(step)
            next_step = WIZARD_STEPS[idx + 1]
        except (ValueError, IndexError):
            next_step = step

        await self._repo.update(
            completed=False,
            current_step=next_step,
            completed_steps=completed_steps,
        )
        logger.info("wizard_step_advanced", from_step=step, to_step=next_step)

    async def go_back(self, from_step: str) -> str:
        """Retreat one step: un-complete the current step and return to the previous one."""
        record = await self._repo.get()
        completed_steps: dict[str, object] = dict(record.completed_steps)

        try:
            idx = WIZARD_STEPS.index(from_step)
        except ValueError:
            return from_step

        if idx == 0:
            return WIZARD_STEPS[0]

        prev_step = WIZARD_STEPS[idx - 1]
        completed_steps.pop(from_step, None)
        completed_steps.pop(prev_step, None)

        await self._repo.update(
            completed=False,
            current_step=prev_step,
            completed_steps=completed_steps,
        )
        logger.info("wizard_step_back", from_step=from_step, to_step=prev_step)
        return prev_step

    async def reset(self) -> None:
        await self._repo.update(
            completed=False,
            current_step=WIZARD_STEPS[0],
            completed_steps={},
        )
        logger.info("wizard_reset")
