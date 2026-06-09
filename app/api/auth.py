"""Auth API endpoints — login, logout, token management."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db_session
from app.persistence.repositories import (
    SqlApiTokenRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from app.security.auth_service import get_auth_service
from app.security.csrf import generate_csrf_token
from app.security.dependencies import (  # noqa: TC001
    CsrfProtected,
    CurrentSession,
    CurrentUser,
    SessionOrTokenUser,
)
from app.services.auth import SESSION_COOKIE_NAME, SESSION_LIFETIME_HOURS, AuthenticationError

router = APIRouter(tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    csrf_token: str


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: dict[str, object] = Field(default_factory=dict)
    machine_id: str | None = None


class TokenCreateResponse(BaseModel):
    id: str
    name: str
    prefix: str
    raw_token: str
    message: str = "Store this token securely — it will not be shown again."


class TokenListItem(BaseModel):
    id: str
    name: str
    prefix: str
    machine_id: str | None
    created_at: str
    last_used_at: str | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Authenticate and obtain a session cookie",
)
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: DbSession,
) -> LoginResponse:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    try:
        session = await auth_svc.login(
            username=body.username,
            password=body.password,
            ip=ip,
            user_agent=ua,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.id,
        httponly=SESSION_COOKIE_HTTPONLY,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=False,  # set True behind TLS; Caddy handles TLS termination
        max_age=SESSION_LIFETIME_HOURS * 3600,
    )
    csrf_token = generate_csrf_token(session.id, session.csrf_secret)
    return LoginResponse(csrf_token=csrf_token)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def logout(
    response: Response,
    session_user: CurrentSession,
    db: DbSession,
) -> None:
    session, _ = session_user
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    await auth_svc.logout(session.id)
    response.delete_cookie(SESSION_COOKIE_NAME)


@router.get(
    "/auth/me",
    summary="Return current authenticated user info",
)
async def me(user: SessionOrTokenUser) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post(
    "/auth/tokens",
    response_model=TokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API token",
)
async def create_token(
    body: TokenCreateRequest,
    _user: CurrentUser,
    _csrf: CsrfProtected,
    db: DbSession,
) -> TokenCreateResponse:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    raw, record = await auth_svc.create_api_token(
        name=body.name, scopes=body.scopes, user_id=_user.id, machine_id=body.machine_id
    )
    return TokenCreateResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        raw_token=raw,
    )


@router.get(
    "/auth/tokens",
    response_model=list[TokenListItem],
    summary="List active API tokens",
)
async def list_tokens(
    _user: CurrentUser,
    db: DbSession,
    machine_id: str | None = None,
) -> list[TokenListItem]:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    if machine_id is not None:
        tokens = await auth_svc.list_api_tokens_for_machine(machine_id)
    else:
        tokens = await auth_svc.list_api_tokens()
    return [
        TokenListItem(
            id=t.id,
            name=t.name,
            prefix=t.prefix,
            machine_id=t.machine_id,
            created_at=t.created_at.isoformat(),
            last_used_at=t.last_used_at.isoformat() if t.last_used_at else None,
        )
        for t in tokens
    ]


@router.delete(
    "/auth/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API token",
)
async def revoke_token(
    token_id: str,
    _user: CurrentUser,
    _csrf: CsrfProtected,
    db: DbSession,
) -> None:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    await auth_svc.revoke_api_token(token_id)
