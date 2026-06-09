"""FastAPI security dependencies — session auth, API token auth, CSRF guard."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports import ApiTokenRecord, SessionRecord, UserRecord
from app.persistence.database import get_db_session
from app.persistence.repositories import (
    SqlApiTokenRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from app.security.auth_service import get_auth_service
from app.security.csrf import validate_csrf_token

logger = structlog.get_logger(__name__)

_SESSION_COOKIE = "wm_session"
_CSRF_HEADER = "X-CSRF-Token"
_BEARER_PREFIX = "Bearer "


# ---------------------------------------------------------------------------
# DB session dep (re-exported for convenience)
# ---------------------------------------------------------------------------
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Session auth
# ---------------------------------------------------------------------------
async def get_current_session_and_user(
    request: Request,
    db: DbSession,
    wm_session: Annotated[str | None, Cookie(alias=_SESSION_COOKIE)] = None,
) -> tuple[SessionRecord, UserRecord]:
    if wm_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    try:
        session, user = await auth_svc.validate_session(wm_session)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from exc

    return session, user


async def get_current_user(
    session_user: Annotated[
        tuple[SessionRecord, UserRecord], Depends(get_current_session_and_user)
    ],
) -> UserRecord:
    return session_user[1]


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]
CurrentSession = Annotated[tuple[SessionRecord, UserRecord], Depends(get_current_session_and_user)]


# ---------------------------------------------------------------------------
# CSRF guard (for state-mutating UI form routes)
# ---------------------------------------------------------------------------
async def require_csrf(
    request: Request,
    session_user: Annotated[
        tuple[SessionRecord, UserRecord], Depends(get_current_session_and_user)
    ],
    x_csrf_token: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
) -> None:
    session, _ = session_user
    form_token = (await request.form()).get(_CSRF_HEADER)
    token = x_csrf_token or (str(form_token) if form_token is not None else "")
    if not token or not validate_csrf_token(str(token), session.id, session.csrf_secret):
        logger.warning("csrf_validation_failed", session_id=session.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


CsrfProtected = Annotated[None, Depends(require_csrf)]


# ---------------------------------------------------------------------------
# API token auth
# ---------------------------------------------------------------------------
async def get_api_token(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiTokenRecord:
    if authorization is None or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raw_token = authorization[len(_BEARER_PREFIX) :]
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    try:
        return await auth_svc.validate_api_token(raw_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


ApiToken = Annotated[ApiTokenRecord, Depends(get_api_token)]
