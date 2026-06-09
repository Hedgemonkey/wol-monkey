"""API-level auth endpoint tests — unauthenticated access, login, logout, me."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_me_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.api
async def test_logout_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 401


@pytest.mark.api
async def test_tokens_list_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/tokens")
    assert resp.status_code == 401


@pytest.mark.api
async def test_token_create_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/tokens", json={"name": "test"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@pytest.mark.api
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    """Login with bad credentials returns 401 (requires DB — skip if no DB dep available)."""
    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        from app.services.auth import AuthenticationError

        mock_svc.login.side_effect = AuthenticationError("bad creds")
        mock_factory.return_value = mock_svc

        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
    assert resp.status_code == 401


@pytest.mark.api
async def test_login_success_sets_cookie(client: AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        fake_session = MagicMock()
        fake_session.id = "fake-session-id"
        fake_session.csrf_secret = "fake-csrf-secret"
        fake_session.expires_at = datetime.now(UTC) + timedelta(hours=12)
        mock_svc.login.return_value = fake_session
        mock_factory.return_value = mock_svc

        with patch("app.api.auth.generate_csrf_token", return_value="fake-csrf-token"):
            resp = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "correct"},
            )

    assert resp.status_code == 200
    assert "wm_session" in resp.cookies
    data = resp.json()
    assert data["csrf_token"] == "fake-csrf-token"


@pytest.mark.api
async def test_login_rejects_missing_body(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={})
    assert resp.status_code == 422
