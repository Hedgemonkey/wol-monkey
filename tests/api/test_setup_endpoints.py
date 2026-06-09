"""API tests for setup wizard endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.setup_state import WIZARD_STEPS


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _mock_setup_state(completed: bool = False, step: str = "welcome") -> MagicMock:
    s = MagicMock()
    s.completed = completed
    s.current_step = step
    s.completed_steps = {}
    return s


@pytest.mark.api
async def test_setup_status_returns_steps(client: AsyncClient) -> None:
    with patch("app.api.setup.SetupStateService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get_state.return_value = {
            "completed": False,
            "current_step": "welcome",
            "completed_steps": {},
        }
        mock_cls.return_value = mock_svc
        resp = await client.get("/api/setup/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["steps"] == WIZARD_STEPS
    assert data["completed"] is False
    assert data["current_step"] == "welcome"


@pytest.mark.api
async def test_setup_complete_returns_410_when_done(client: AsyncClient) -> None:
    with patch("app.api.setup.SetupStateService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.is_complete.return_value = True
        mock_cls.return_value = mock_svc
        resp = await client.post("/api/setup/complete")

    assert resp.status_code == 410


@pytest.mark.api
async def test_setup_admin_conflict_if_already_exists(client: AsyncClient) -> None:
    from app.services.auth import AuthenticationError

    with (
        patch("app.api.setup.SetupStateService") as mock_state_cls,
        patch("app.api.setup.get_auth_service") as mock_auth_factory,
    ):
        mock_state = AsyncMock()
        mock_state.is_complete.return_value = False
        mock_state_cls.return_value = mock_state

        mock_auth = AsyncMock()
        mock_auth.create_admin.side_effect = AuthenticationError("Admin account already exists")
        mock_auth_factory.return_value = mock_auth

        resp = await client.post(
            "/api/setup/admin",
            json={"username": "admin", "password": "longpassword123"},
        )

    assert resp.status_code == 409


@pytest.mark.api
async def test_setup_admin_created_successfully(client: AsyncClient) -> None:
    with (
        patch("app.api.setup.SetupStateService") as mock_state_cls,
        patch("app.api.setup.get_auth_service") as mock_auth_factory,
    ):
        mock_state = AsyncMock()
        mock_state.is_complete.return_value = False
        mock_state_cls.return_value = mock_state

        fake_user = MagicMock()
        fake_user.id = "user-1"
        fake_user.username = "admin"
        mock_auth = AsyncMock()
        mock_auth.create_admin.return_value = fake_user
        mock_auth_factory.return_value = mock_auth

        resp = await client.post(
            "/api/setup/admin",
            json={"username": "admin", "password": "securepassword123"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "admin"


@pytest.mark.api
async def test_setup_network_stores_settings(client: AsyncClient) -> None:
    with (
        patch("app.api.setup.SetupStateService") as mock_state_cls,
        patch("app.api.setup.SettingsService") as mock_settings_cls,
    ):
        mock_state = AsyncMock()
        mock_state.is_complete.return_value = False
        mock_state_cls.return_value = mock_state

        mock_settings = AsyncMock()
        mock_settings_cls.return_value = mock_settings

        resp = await client.post(
            "/api/setup/network",
            json={
                "wake_interface": "eth0",
                "default_wake_strategy": "udp_broadcast",
                "default_poll_timeout_s": 60,
            },
        )

    assert resp.status_code == 200
    assert mock_settings.set.await_count == 3


@pytest.mark.api
async def test_setup_admin_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/setup/admin",
        json={"username": "admin", "password": "short"},
    )
    assert resp.status_code == 422
