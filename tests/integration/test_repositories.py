"""Integration tests for repository implementations against a real Postgres."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories import (
    SqlApiTokenRepository,
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
            strategy="udp_broadcast",
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


# ---------------------------------------------------------------------------
# ApiToken repository
# ---------------------------------------------------------------------------
class TestApiTokenRepository:
    async def _make_user(self, db_session: AsyncSession, suffix: str = "1") -> str:
        repo = SqlUserRepository(db_session)
        u = await repo.create(username=f"tokenuser{suffix}", password_hash="h")
        return u.id

    async def _make_machine(self, db_session: AsyncSession, suffix: str = "1") -> str:
        repo = SqlMachineRepository(db_session)
        m = await repo.create(
            name=f"TokenMachine{suffix}",
            ip_address="10.0.0.1",
            mac_address=f"aa:bb:cc:dd:ee:{int(suffix) % 256:02x}",
            ssh_port=22,
            wake_strategy="etherwake",
        )
        return m.id

    async def test_create_global_token(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "2")
        repo = SqlApiTokenRepository(db_session)
        token = await repo.create(
            name="global key",
            token_hash="hash_global",
            prefix="wm_1",
            scopes={},
            user_id=user_id,
        )
        assert token.name == "global key"
        assert token.machine_id is None
        assert token.user_id == user_id

    async def test_create_machine_scoped_token(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "3")
        machine_id = await self._make_machine(db_session, "3")
        repo = SqlApiTokenRepository(db_session)
        token = await repo.create(
            name="laptop key",
            token_hash="hash_laptop",
            prefix="wm_2",
            scopes={},
            user_id=user_id,
            machine_id=machine_id,
        )
        assert token.machine_id == machine_id

    async def test_list_active_returns_unrevoked(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "4")
        repo = SqlApiTokenRepository(db_session)
        await repo.create(
            name="active", token_hash="hash_active", prefix="wm_3", scopes={}, user_id=user_id
        )
        await repo.create(
            name="to_revoke", token_hash="hash_revoke", prefix="wm_4", scopes={}, user_id=user_id
        )
        tokens_before = await repo.list_active()
        names_before = {t.name for t in tokens_before}
        assert "active" in names_before
        assert "to_revoke" in names_before

        # Revoke one
        revoke_id = next(t.id for t in tokens_before if t.name == "to_revoke")
        await repo.revoke(revoke_id)
        await db_session.commit()

        tokens_after = await repo.list_active()
        names_after = {t.name for t in tokens_after}
        assert "active" in names_after
        assert "to_revoke" not in names_after

    async def test_list_for_machine_filters_correctly(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "5")
        machine_id = await self._make_machine(db_session, "5")
        repo = SqlApiTokenRepository(db_session)

        # Create one token scoped to the machine, one global
        await repo.create(
            name="scoped",
            token_hash="hash_scoped5",
            prefix="wm_5",
            scopes={},
            user_id=user_id,
            machine_id=machine_id,
        )
        await repo.create(
            name="unscoped",
            token_hash="hash_unscoped5",
            prefix="wm_6",
            scopes={},
            user_id=user_id,
            machine_id=None,
        )

        machine_tokens = await repo.list_for_machine(machine_id)
        assert len(machine_tokens) == 1
        assert machine_tokens[0].name == "scoped"

    async def test_list_for_machine_invalid_uuid_returns_empty(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlApiTokenRepository(db_session)
        result = await repo.list_for_machine("not-a-uuid")
        assert result == []

    async def test_get_by_hash_returns_token(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "6")
        repo = SqlApiTokenRepository(db_session)
        await repo.create(
            name="hashtest", token_hash="hash_by_hash6", prefix="wm_7", scopes={}, user_id=user_id
        )
        found = await repo.get_by_hash("hash_by_hash6")
        assert found is not None
        assert found.name == "hashtest"

    async def test_get_by_hash_revoked_returns_none(self, db_session: AsyncSession) -> None:
        user_id = await self._make_user(db_session, "7")
        repo = SqlApiTokenRepository(db_session)
        tok = await repo.create(
            name="revokedtest",
            token_hash="hash_revoked7",
            prefix="wm_8",
            scopes={},
            user_id=user_id,
        )
        await repo.revoke(tok.id)
        await db_session.commit()
        found = await repo.get_by_hash("hash_revoked7")
        assert found is None

    async def test_machine_delete_nullifies_token_machine_id(
        self, db_session: AsyncSession
    ) -> None:
        """ON DELETE SET NULL: deleting a machine should null out token.machine_id."""
        user_id = await self._make_user(db_session, "8")
        machine_id = await self._make_machine(db_session, "8")
        token_repo = SqlApiTokenRepository(db_session)
        tok = await token_repo.create(
            name="setnull",
            token_hash="hash_setnull8",
            prefix="wm_9",
            scopes={},
            user_id=user_id,
            machine_id=machine_id,
        )
        assert tok.machine_id == machine_id

        # Delete the machine
        machine_repo = SqlMachineRepository(db_session)
        await machine_repo.delete(machine_id)
        await db_session.commit()

        # Token should still exist but machine_id nulled
        found = await token_repo.get_by_hash("hash_setnull8")
        assert found is not None
        assert found.machine_id is None
