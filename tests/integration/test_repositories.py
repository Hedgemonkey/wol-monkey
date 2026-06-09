"""Integration tests for repository implementations against a real Postgres."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories import (
    SqlMachineRepository,
    SqlSessionRepository,
    SqlSettingsRepository,
    SqlSetupStateRepository,
    SqlUserRepository,
    SqlWakeAttemptRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# User repository
# ---------------------------------------------------------------------------
class TestUserRepository:
    async def test_create_and_get_by_username(self, db_session: AsyncSession) -> None:
        repo = SqlUserRepository(db_session)
        user = await repo.create(username="testadmin", password_hash="hashed_pw_here")
        assert user.username == "testadmin"
        assert user.role == "admin"

        fetched = await repo.get_by_username("testadmin")
        assert fetched is not None
        assert fetched.id == user.id

    async def test_get_by_id(self, db_session: AsyncSession) -> None:
        repo = SqlUserRepository(db_session)
        user = await repo.create(username="user2", password_hash="h")
        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.username == "user2"

    async def test_count(self, db_session: AsyncSession) -> None:
        repo = SqlUserRepository(db_session)
        await repo.create(username="countuser", password_hash="h")
        count = await repo.count()
        assert count >= 1

    async def test_update_last_login(self, db_session: AsyncSession) -> None:
        repo = SqlUserRepository(db_session)
        user = await repo.create(username="loginuser", password_hash="h")
        assert user.last_login_at is None
        await repo.update_last_login(user.id)
        await db_session.commit()
        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.last_login_at is not None

    async def test_get_nonexistent_user_returns_none(self, db_session: AsyncSession) -> None:
        repo = SqlUserRepository(db_session)
        result = await repo.get_by_username("doesnotexist")
        assert result is None


# ---------------------------------------------------------------------------
# Machine repository
# ---------------------------------------------------------------------------
class TestMachineRepository:
    def _machine_kwargs(self, suffix: str = "") -> dict:
        return {
            "name": f"Test Machine{suffix}",
            "ip_address": "172.24.0.2",
            "mac_address": f"d8:bb:c1:cd:d1:{suffix or 'c7'}",
            "ssh_port": 22,
            "wake_interface": "enP4p65s0",
            "wake_strategy": "etherwake",
        }

    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        repo = SqlMachineRepository(db_session)
        machine = await repo.create(**self._machine_kwargs())
        assert machine.name == "Test Machine"
        assert machine.mac_address is not None
        assert machine.enabled is True

        fetched = await repo.get_by_id(machine.id)
        assert fetched is not None
        assert fetched.id == machine.id

    async def test_list_all(self, db_session: AsyncSession) -> None:
        repo = SqlMachineRepository(db_session)
        await repo.create(**self._machine_kwargs("aa"))
        machines = await repo.list_all()
        assert len(machines) >= 1

    async def test_update(self, db_session: AsyncSession) -> None:
        repo = SqlMachineRepository(db_session)
        machine = await repo.create(**self._machine_kwargs("bb"))
        updated = await repo.update(machine.id, name="Renamed")
        assert updated is not None
        assert updated.name == "Renamed"

    async def test_delete(self, db_session: AsyncSession) -> None:
        repo = SqlMachineRepository(db_session)
        machine = await repo.create(**self._machine_kwargs("cc"))
        deleted = await repo.delete(machine.id)
        assert deleted is True
        assert await repo.get_by_id(machine.id) is None

    async def test_count(self, db_session: AsyncSession) -> None:
        repo = SqlMachineRepository(db_session)
        await repo.create(**self._machine_kwargs("dd"))
        count = await repo.count()
        assert count >= 1


# ---------------------------------------------------------------------------
# WakeAttempt repository
# ---------------------------------------------------------------------------
class TestWakeAttemptRepository:
    async def _make_machine(self, db_session: AsyncSession, mac_last: str = "e1") -> str:
        repo = SqlMachineRepository(db_session)
        m = await repo.create(
            name=f"M{mac_last}",
            ip_address="172.24.0.2",
            mac_address=f"d8:bb:c1:cd:d2:{mac_last}",
            ssh_port=22,
            wake_strategy="etherwake",
        )
        return m.id

    async def test_create_attempt(self, db_session: AsyncSession) -> None:
        machine_id = await self._make_machine(db_session)
        repo = SqlWakeAttemptRepository(db_session)
        attempt = await repo.create(
            machine_id=machine_id,
            actor_type="user",
            actor_id="some-user-id",
            strategy="etherwake",
        )
        assert attempt.status == "pending"
        assert attempt.machine_id == machine_id

    async def test_update_status(self, db_session: AsyncSession) -> None:
        machine_id = await self._make_machine(db_session, "f1")
        repo = SqlWakeAttemptRepository(db_session)
        attempt = await repo.create(
            machine_id=machine_id,
            actor_type="user",
            actor_id="uid",
            strategy="udp",
        )
        await repo.update_status(attempt.id, "sent")
        await db_session.commit()
        fetched = await repo.get_by_id(attempt.id)
        assert fetched is not None
        assert fetched.status == "sent"

    async def test_get_active_for_machine(self, db_session: AsyncSession) -> None:
        machine_id = await self._make_machine(db_session, "a2")
        repo = SqlWakeAttemptRepository(db_session)
        await repo.create(
            machine_id=machine_id, actor_type="user", actor_id="u", strategy="etherwake"
        )
        active = await repo.get_active_for_machine(machine_id)
        assert active is not None
        assert active.status in ("pending", "sent", "waking")


# ---------------------------------------------------------------------------
# Session repository
# ---------------------------------------------------------------------------
class TestSessionRepository:
    async def _make_user(self, db_session: AsyncSession, uname: str) -> str:
        repo = SqlUserRepository(db_session)
        u = await repo.create(username=uname, password_hash="h")
        return u.id

    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "sessuser1")
        repo = SqlSessionRepository(db_session)
        sess = await repo.create(
            user_id=user_id,
            csrf_secret="secret123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            ip="192.168.1.1",
        )
        assert sess.revoked is False
        fetched = await repo.get_by_id(sess.id)
        assert fetched is not None
        assert fetched.csrf_secret == "secret123"

    async def test_revoke(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "sessuser2")
        repo = SqlSessionRepository(db_session)
        sess = await repo.create(
            user_id=user_id,
            csrf_secret="s",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await repo.revoke(sess.id)
        await db_session.commit()
        fetched = await repo.get_by_id(sess.id)
        assert fetched is not None
        assert fetched.revoked is True


# ---------------------------------------------------------------------------
# Settings repository
# ---------------------------------------------------------------------------
class TestSettingsRepository:
    async def test_set_and_get(self, db_session: AsyncSession) -> None:
        repo = SqlSettingsRepository(db_session)
        await repo.set("access_mode", "local")
        value = await repo.get("access_mode")
        assert value == "local"

    async def test_get_missing_returns_none(self, db_session: AsyncSession) -> None:
        repo = SqlSettingsRepository(db_session)
        value = await repo.get("nonexistent_key_xyz")
        assert value is None

    async def test_overwrite(self, db_session: AsyncSession) -> None:
        repo = SqlSettingsRepository(db_session)
        await repo.set("probe_interval", 30)
        await repo.set("probe_interval", 60)
        value = await repo.get("probe_interval")
        assert value == 60

    async def test_get_all(self, db_session: AsyncSession) -> None:
        repo = SqlSettingsRepository(db_session)
        await repo.set("key_a", "alpha")
        await repo.set("key_b", 42)
        all_settings = await repo.get_all()
        assert "key_a" in all_settings
        assert all_settings["key_b"] == 42


# ---------------------------------------------------------------------------
# SetupState repository
# ---------------------------------------------------------------------------
class TestSetupStateRepository:
    async def test_get_creates_if_missing(self, db_session: AsyncSession) -> None:
        repo = SqlSetupStateRepository(db_session)
        state = await repo.get()
        assert state.id == 1
        assert state.completed is False

    async def test_update(self, db_session: AsyncSession) -> None:
        repo = SqlSetupStateRepository(db_session)
        await repo.get()  # ensure exists
        updated = await repo.update(current_step="create_admin")
        assert updated.current_step == "create_admin"
