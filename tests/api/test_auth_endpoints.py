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


# ---------------------------------------------------------------------------
# Token creation / listing / revoke (authenticated, mocked service)
# ---------------------------------------------------------------------------
def _auth_overrides(app, fake_user, fake_session):
    from unittest.mock import AsyncMock

    from app.persistence.database import get_db_session
    from app.security.dependencies import (
        get_current_session_and_user,
        get_user_from_session_or_token,
        require_csrf,
    )

    async def _fake_db():
        yield AsyncMock()

    async def _noop_csrf():
        return None

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_current_session_and_user] = lambda: (fake_session, fake_user)
    app.dependency_overrides[get_user_from_session_or_token] = lambda: fake_user
    app.dependency_overrides[require_csrf] = _noop_csrf
    return app


@pytest.mark.api
async def test_create_token_with_machine_id(app) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_user = MagicMock()
    fake_user.id = "user-uuid-1"
    fake_session = MagicMock()
    fake_session.csrf_secret = "secret"

    _auth_overrides(app, fake_user, fake_session)

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        fake_record = MagicMock()
        fake_record.id = "token-uuid"
        fake_record.name = "laptop key"
        fake_record.prefix = "wm_1"
        fake_record.machine_id = "machine-uuid-1"
        mock_svc.create_api_token.return_value = ("raw_tok_value", fake_record)
        mock_factory.return_value = mock_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/auth/tokens",
                json={"name": "laptop key", "machine_id": "machine-uuid-1"},
                headers={"X-CSRF-Token": "any"},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["raw_token"] == "raw_tok_value"
    assert data["name"] == "laptop key"
    mock_svc.create_api_token.assert_awaited_once_with(
        name="laptop key", scopes={}, user_id="user-uuid-1", machine_id="machine-uuid-1"
    )


@pytest.mark.api
async def test_create_token_without_machine_id(app) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_user = MagicMock()
    fake_user.id = "user-uuid-2"
    fake_session = MagicMock()
    fake_session.csrf_secret = "secret"

    _auth_overrides(app, fake_user, fake_session)

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        fake_record = MagicMock()
        fake_record.id = "token-uuid-2"
        fake_record.name = "global key"
        fake_record.prefix = "wm_2"
        fake_record.machine_id = None
        mock_svc.create_api_token.return_value = ("raw_global", fake_record)
        mock_factory.return_value = mock_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/auth/tokens",
                json={"name": "global key"},
                headers={"X-CSRF-Token": "any"},
            )

    assert resp.status_code == 201
    mock_svc.create_api_token.assert_awaited_once_with(
        name="global key", scopes={}, user_id="user-uuid-2", machine_id=None
    )


@pytest.mark.api
async def test_list_tokens_includes_machine_id(app) -> None:
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_user = MagicMock()
    fake_session = MagicMock()
    _auth_overrides(app, fake_user, fake_session)

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        t = MagicMock()
        t.id = "tid"
        t.name = "my token"
        t.prefix = "wm_3"
        t.machine_id = "mid-abc"
        t.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        t.last_used_at = None
        mock_svc.list_api_tokens.return_value = [t]
        mock_factory.return_value = mock_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/auth/tokens")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["machine_id"] == "mid-abc"
    assert items[0]["name"] == "my token"


@pytest.mark.api
async def test_list_tokens_machine_id_filter_calls_correct_service_method(app) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_user = MagicMock()
    fake_session = MagicMock()
    _auth_overrides(app, fake_user, fake_session)

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        mock_svc.list_api_tokens_for_machine.return_value = []
        mock_factory.return_value = mock_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/auth/tokens?machine_id=some-machine-id")

    assert resp.status_code == 200
    mock_svc.list_api_tokens_for_machine.assert_awaited_once_with("some-machine-id")
    mock_svc.list_api_tokens.assert_not_awaited()


@pytest.mark.api
async def test_revoke_token(app) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_user = MagicMock()
    fake_session = MagicMock()
    fake_session.csrf_secret = "secret"
    _auth_overrides(app, fake_user, fake_session)

    with patch("app.api.auth.get_auth_service") as mock_factory:
        mock_svc = AsyncMock()
        mock_factory.return_value = mock_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(
                "/api/auth/tokens/token-id-123",
                headers={"X-CSRF-Token": "any"},
            )

    assert resp.status_code == 204
    mock_svc.revoke_api_token.assert_awaited_once_with("token-id-123")
