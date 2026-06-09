"""Security/auth tests — password hashing, token generation, CSRF, login/logout."""

import pytest

from app.security.password import hash_password, needs_rehash, verify_password
from app.security.tokens import generate_token, hash_token


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
@pytest.mark.security
class TestPasswordHashing:
    def test_hash_is_not_plaintext(self) -> None:
        h = hash_password("mysecret")
        assert h != "mysecret"
        assert len(h) > 20

    def test_verify_correct_password(self) -> None:
        h = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", h) is True

    def test_verify_wrong_password(self) -> None:
        h = hash_password("correct-horse-battery")
        assert verify_password("wrong-password", h) is False

    def test_two_hashes_of_same_password_differ(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # argon2 uses a random salt

    def test_needs_rehash_fresh_hash(self) -> None:
        h = hash_password("fresh")
        assert needs_rehash(h) is False


# ---------------------------------------------------------------------------
# API token generation
# ---------------------------------------------------------------------------
@pytest.mark.security
class TestTokenGeneration:
    def test_generate_token_structure(self) -> None:
        raw, prefix, _token_hash = generate_token()
        assert raw.startswith("wm_")
        parts = raw.split("_")
        assert len(parts) == 3
        assert parts[1] == prefix

    def test_token_hash_is_sha256(self) -> None:
        _raw, _, token_hash = generate_token()
        assert len(token_hash) == 64  # SHA-256 hex digest

    def test_hash_token_is_deterministic(self) -> None:
        raw, _, _ = generate_token()
        h1 = hash_token(raw)
        h2 = hash_token(raw)
        assert h1 == h2

    def test_different_tokens_different_hashes(self) -> None:
        raw1, _, _ = generate_token()
        raw2, _, _ = generate_token()
        assert hash_token(raw1) != hash_token(raw2)

    def test_raw_token_never_equals_hash(self) -> None:
        raw, _, token_hash = generate_token()
        assert raw != token_hash


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
@pytest.mark.security
class TestCsrf:
    def test_valid_csrf_token(self) -> None:
        from app.security.csrf import generate_csrf_secret, generate_csrf_token, validate_csrf_token

        secret = generate_csrf_secret()
        session_id = "test-session-id"
        token = generate_csrf_token(session_id, secret)
        assert validate_csrf_token(token, session_id, secret) is True

    def test_wrong_session_id_rejected(self) -> None:
        from app.security.csrf import generate_csrf_secret, generate_csrf_token, validate_csrf_token

        secret = generate_csrf_secret()
        token = generate_csrf_token("sid-A", secret)
        assert validate_csrf_token(token, "sid-B", secret) is False

    def test_wrong_secret_rejected(self) -> None:
        from app.security.csrf import generate_csrf_secret, generate_csrf_token, validate_csrf_token

        secret = generate_csrf_secret()
        token = generate_csrf_token("sid", secret)
        assert validate_csrf_token(token, "sid", "wrong-secret") is False

    def test_tampered_token_rejected(self) -> None:
        from app.security.csrf import generate_csrf_secret, generate_csrf_token, validate_csrf_token

        secret = generate_csrf_secret()
        token = generate_csrf_token("sid", secret)
        tampered = token[:-4] + "XXXX"
        assert validate_csrf_token(tampered, "sid", secret) is False

    def test_empty_token_rejected(self) -> None:
        from app.security.csrf import generate_csrf_secret, validate_csrf_token

        secret = generate_csrf_secret()
        assert validate_csrf_token("", "sid", secret) is False


# ---------------------------------------------------------------------------
# Auth service (unit — no DB)
# ---------------------------------------------------------------------------
@pytest.mark.security
class TestAuthServiceUnit:
    def _make_service(self):  # type: ignore[no-untyped-def]
        from unittest.mock import AsyncMock

        from app.services.auth import AuthService

        user_repo = AsyncMock()
        session_repo = AsyncMock()
        token_repo = AsyncMock()
        return AuthService(user_repo, session_repo, token_repo), user_repo, session_repo, token_repo

    async def test_admin_exists_false_when_count_zero(self) -> None:
        svc, user_repo, _, _ = self._make_service()
        user_repo.count.return_value = 0
        assert await svc.admin_exists() is False

    async def test_admin_exists_true_when_count_nonzero(self) -> None:
        svc, user_repo, _, _ = self._make_service()
        user_repo.count.return_value = 1
        assert await svc.admin_exists() is True

    async def test_create_admin_raises_if_exists(self) -> None:
        from app.services.auth import AuthenticationError

        svc, user_repo, _, _ = self._make_service()
        user_repo.count.return_value = 1
        with pytest.raises(AuthenticationError):
            await svc.create_admin("admin", "password")

    async def test_login_invalid_username(self) -> None:
        from app.services.auth import AuthenticationError

        svc, user_repo, _, _ = self._make_service()
        user_repo.get_by_username.return_value = None
        with pytest.raises(AuthenticationError):
            await svc.login("baduser", "pw")

    async def test_login_wrong_password(self) -> None:
        from unittest.mock import MagicMock

        from app.security.password import hash_password
        from app.services.auth import AuthenticationError

        svc, user_repo, _, _ = self._make_service()
        fake_user = MagicMock()
        fake_user.password_hash = hash_password("correct")
        user_repo.get_by_username.return_value = fake_user
        with pytest.raises(AuthenticationError):
            await svc.login("user", "wrong")

    async def test_validate_session_expired(self) -> None:
        from datetime import UTC, datetime, timedelta
        from unittest.mock import MagicMock

        from app.services.auth import AuthenticationError

        svc, _, session_repo, _ = self._make_service()
        fake_session = MagicMock()
        fake_session.revoked = False
        fake_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session_repo.get_by_id.return_value = fake_session
        with pytest.raises(AuthenticationError, match="expired"):
            await svc.validate_session("sid")

    async def test_validate_session_revoked(self) -> None:
        from unittest.mock import MagicMock

        from app.services.auth import AuthenticationError

        svc, _, session_repo, _ = self._make_service()
        fake_session = MagicMock()
        fake_session.revoked = True
        session_repo.get_by_id.return_value = fake_session
        with pytest.raises(AuthenticationError):
            await svc.validate_session("sid")
