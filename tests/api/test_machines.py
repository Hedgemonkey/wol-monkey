"""API tests for machines CRUD and wake endpoints."""

from __future__ import annotations

from collections.abc import Generator  # noqa: TC003
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.persistence.database import get_db_session
from app.security.dependencies import get_current_session_and_user, get_user_from_session_or_token


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _fake_user() -> MagicMock:
    u = MagicMock()
    u.id = "user-1"
    u.username = "admin"
    u.role = "admin"
    return u


def _fake_session() -> MagicMock:
    s = MagicMock()
    s.id = "session-1"
    s.user_id = "user-1"
    s.revoked = False
    s.expires_at = datetime.now(UTC).replace(year=2099)
    s.csrf_secret = "secret"
    return s


def _fake_machine(mid: str = "m1") -> MagicMock:
    m = MagicMock()
    m.id = mid
    m.name = "Test Box"
    m.ip_address = "192.168.1.10"
    m.mac_address = "aa:bb:cc:dd:ee:ff"
    m.ssh_port = 22
    m.hostname = None
    m.wake_interface = None
    m.wake_strategy = "etherwake"
    m.broadcast_address = None
    m.enabled = True
    m.created_at = datetime.now(UTC)
    m.updated_at = datetime.now(UTC)
    return m


@contextmanager
def _auth_overrides(app, user=None, session=None) -> Generator[None, None, None]:
    u = user or _fake_user()
    s = session or _fake_session()

    async def _fake_auth():
        return s, u

    async def _fake_user_only():
        return u

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_session_and_user] = _fake_auth
    app.dependency_overrides[get_user_from_session_or_token] = _fake_user_only
    app.dependency_overrides[get_db_session] = _fake_db
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Machines list
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_list_machines_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/machines")
    assert resp.status_code == 401


@pytest.mark.api
async def test_list_machines_returns_list(client: AsyncClient, app) -> None:
    with _auth_overrides(app), patch("app.api.machines.SqlMachineRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.list_all.return_value = [_fake_machine("m1"), _fake_machine("m2")]
        mock_repo_cls.return_value = mock_repo
        resp = await client.get("/api/machines")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "m1"


@pytest.mark.api
async def test_get_machine_not_found(client: AsyncClient, app) -> None:
    with _auth_overrides(app), patch("app.api.machines.SqlMachineRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo
        resp = await client.get("/api/machines/nonexistent")

    assert resp.status_code == 404


@pytest.mark.api
async def test_get_machine_success(client: AsyncClient, app) -> None:
    with _auth_overrides(app), patch("app.api.machines.SqlMachineRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = _fake_machine()
        mock_repo_cls.return_value = mock_repo
        resp = await client.get("/api/machines/m1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "m1"


# ---------------------------------------------------------------------------
# Machine create
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_create_machine_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/machines",
        json={"name": "Box", "ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
    )
    assert resp.status_code == 401


@pytest.mark.api
async def test_create_machine_success(client: AsyncClient, app) -> None:
    with (
        _auth_overrides(app),
        patch("app.api.machines.SqlMachineRepository") as mock_repo_cls,
        patch("app.security.dependencies.validate_csrf_token", return_value=True),
    ):
        mock_repo = AsyncMock()
        mock_repo.create.return_value = _fake_machine()
        mock_repo_cls.return_value = mock_repo
        resp = await client.post(
            "/api/machines",
            json={
                "name": "Test Box",
                "ip_address": "192.168.1.10",
                "mac_address": "aa:bb:cc:dd:ee:ff",
            },
            headers={"X-CSRF-Token": "fake-token"},
        )

    assert resp.status_code == 201
    assert resp.json()["mac_address"] == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# Delete machine
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_delete_machine_not_found(client: AsyncClient, app) -> None:
    with (
        _auth_overrides(app),
        patch("app.api.machines.SqlMachineRepository") as mock_repo_cls,
        patch("app.security.dependencies.validate_csrf_token", return_value=True),
    ):
        mock_repo = AsyncMock()
        mock_repo.delete.return_value = False
        mock_repo_cls.return_value = mock_repo
        resp = await client.delete(
            "/api/machines/nonexistent",
            headers={"X-CSRF-Token": "fake-token"},
        )

    assert resp.status_code == 404


@pytest.mark.api
async def test_delete_machine_success(client: AsyncClient, app) -> None:
    with (
        _auth_overrides(app),
        patch("app.api.machines.SqlMachineRepository") as mock_repo_cls,
        patch("app.security.dependencies.validate_csrf_token", return_value=True),
    ):
        mock_repo = AsyncMock()
        mock_repo.delete.return_value = True
        mock_repo_cls.return_value = mock_repo
        resp = await client.delete(
            "/api/machines/m1",
            headers={"X-CSRF-Token": "fake-token"},
        )

    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Wake endpoint
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_wake_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post("/api/machines/m1/wake", json={})
    assert resp.status_code == 401


@pytest.mark.api
async def test_wake_machine_not_found(client: AsyncClient, app) -> None:
    with (
        _auth_overrides(app),
        patch("app.api.wake.SqlMachineRepository") as mock_repo_cls,
        patch("app.security.dependencies.validate_csrf_token", return_value=True),
    ):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo
        resp = await client.post(
            "/api/machines/m1/wake",
            json={},
            headers={"X-CSRF-Token": "fake-token"},
        )

    assert resp.status_code == 404


@pytest.mark.api
async def test_wake_machine_queued(client: AsyncClient, app) -> None:
    fake_attempt = MagicMock()
    fake_attempt.id = "attempt-1"
    fake_attempt.wake_strategy = "etherwake"

    with (
        _auth_overrides(app),
        patch("app.api.wake.SqlMachineRepository") as mock_machine_cls,
        patch("app.api.wake.SqlWakeAttemptRepository") as mock_attempt_cls,
        patch("app.api.wake.JobQueue") as mock_queue_cls,
        patch("app.api.wake.get_session_factory"),
        patch("app.security.dependencies.validate_csrf_token", return_value=True),
    ):
        mock_machine_repo = AsyncMock()
        mock_machine_repo.get_by_id.return_value = _fake_machine()
        mock_machine_cls.return_value = mock_machine_repo

        mock_attempt_repo = AsyncMock()
        mock_attempt_repo.create.return_value = fake_attempt
        mock_attempt_cls.return_value = mock_attempt_repo

        mock_queue = AsyncMock()
        mock_queue_cls.return_value = mock_queue

        resp = await client.post(
            "/api/machines/m1/wake",
            json={},
            headers={"X-CSRF-Token": "fake-token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["attempt_id"] == "attempt-1"
    assert data["status"] == "pending"
