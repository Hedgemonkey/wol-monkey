"""Authentication service — login, logout, session management, token auth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from app.domain.ports import (  # noqa: TC001
    ApiTokenRecord,
    ApiTokenRepository,
    SessionRecord,
    SessionRepository,
    UserRecord,
    UserRepository,
)
from app.security.csrf import generate_csrf_secret
from app.security.password import hash_password, needs_rehash, verify_password
from app.security.tokens import generate_token, hash_token

logger = structlog.get_logger(__name__)

SESSION_LIFETIME_HOURS = 12
SESSION_COOKIE_NAME = "wm_session"


class AuthenticationError(Exception):
    pass


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        token_repo: ApiTokenRepository,
    ) -> None:
        self._users = user_repo
        self._sessions = session_repo
        self._tokens = token_repo

    # ------------------------------------------------------------------
    # Admin bootstrap
    # ------------------------------------------------------------------
    async def admin_exists(self) -> bool:
        return await self._users.count() > 0

    async def create_admin(self, username: str, password: str) -> UserRecord:
        if await self.admin_exists():
            raise AuthenticationError("Admin account already exists")
        pw_hash = hash_password(password)
        user = await self._users.create(username=username, password_hash=pw_hash)
        logger.info("admin_created", user_id=user.id)
        return user

    # ------------------------------------------------------------------
    # Login / logout
    # ------------------------------------------------------------------
    async def login(
        self,
        username: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionRecord:
        user = await self._users.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            logger.warning("login_failed", username=username, ip=ip)
            raise AuthenticationError("Invalid credentials")

        if needs_rehash(user.password_hash):
            new_hash = hash_password(password)
            await self._users.update_password_hash(user.id, new_hash)
            logger.info("password_rehashed", user_id=user.id)

        expires_at = datetime.now(UTC) + timedelta(hours=SESSION_LIFETIME_HOURS)
        csrf_secret = generate_csrf_secret()
        session = await self._sessions.create(
            user_id=user.id,
            csrf_secret=csrf_secret,
            expires_at=expires_at,
            ip=ip,
            user_agent=user_agent,
        )
        await self._users.update_last_login(user.id)
        logger.info("login_success", user_id=user.id, session_id=session.id, ip=ip)
        return session

    async def logout(self, session_id: str) -> None:
        await self._sessions.revoke(session_id)
        logger.info("logout", session_id=session_id)

    # ------------------------------------------------------------------
    # Session validation
    # ------------------------------------------------------------------
    async def validate_session(self, session_id: str) -> tuple[SessionRecord, UserRecord]:
        session = await self._sessions.get_by_id(session_id)
        if session is None or session.revoked:
            raise AuthenticationError("Invalid or revoked session")
        if session.expires_at < datetime.now(UTC):
            raise AuthenticationError("Session expired")
        user = await self._users.get_by_id(session.user_id)
        if user is None:
            raise AuthenticationError("User not found")
        return session, user

    # ------------------------------------------------------------------
    # API token management
    # ------------------------------------------------------------------
    async def create_api_token(
        self, name: str, scopes: dict[str, object]
    ) -> tuple[str, ApiTokenRecord]:
        """Returns (raw_token, record). raw_token shown once — never stored."""
        raw, prefix, token_hash = generate_token()
        record = await self._tokens.create(
            name=name, token_hash=token_hash, prefix=prefix, scopes=scopes
        )
        logger.info("api_token_created", token_id=record.id, name=name)
        return raw, record

    async def validate_api_token(self, raw_token: str) -> ApiTokenRecord:
        token_hash = hash_token(raw_token)
        record = await self._tokens.get_by_hash(token_hash)
        if record is None:
            raise AuthenticationError("Invalid API token")
        if record.revoked_at is not None:
            raise AuthenticationError("API token has been revoked")
        await self._tokens.touch_last_used(record.id)
        return record

    async def revoke_api_token(self, token_id: str) -> None:
        await self._tokens.revoke(token_id)
        logger.info("api_token_revoked", token_id=token_id)

    async def list_api_tokens(self) -> list[ApiTokenRecord]:
        return await self._tokens.list_active()
