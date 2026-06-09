"""Web UI routes — server-rendered Jinja2 pages."""

from __future__ import annotations

import pathlib
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db_session
from app.persistence.repositories import (
    SqlApiTokenRepository,
    SqlMachineRepository,
    SqlSessionRepository,
    SqlSettingsRepository,
    SqlSetupStateRepository,
    SqlUserRepository,
)
from app.security.auth_service import get_auth_service
from app.security.csrf import generate_csrf_token
from app.services.auth import SESSION_COOKIE_NAME, SESSION_LIFETIME_HOURS, AuthenticationError
from app.services.settings import SettingsService
from app.services.setup_state import WIZARD_STEPS, SetupStateService

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


async def _get_csrf(request: Request, db: AsyncSession) -> str:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return ""
    try:
        auth_svc = get_auth_service(
            user_repo=SqlUserRepository(db),
            session_repo=SqlSessionRepository(db),
            token_repo=SqlApiTokenRepository(db),
        )
        session, _ = await auth_svc.validate_session(session_id)
        return generate_csrf_token(session.id, session.csrf_secret)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Setup wizard
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def root(request: Request, db: DbSession) -> Response:
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    if await setup_svc.is_complete():
        return _redirect("/machines")
    state = await setup_svc.get_state()
    return _redirect(f"/setup/{state['current_step']}")


@router.get("/setup/{step}", response_class=HTMLResponse)
async def setup_page(step: str, request: Request, db: DbSession) -> Response:
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    if await setup_svc.is_complete():
        return _redirect("/machines")
    state = await setup_svc.get_state()
    if step not in WIZARD_STEPS:
        return _redirect(f"/setup/{state['current_step']}")
    step_index = WIZARD_STEPS.index(step)
    return templates.TemplateResponse(
        request,
        "setup_wizard.html",
        {
            "step": step,
            "steps": WIZARD_STEPS,
            "step_index": step_index,
            "total_steps": len(WIZARD_STEPS),
            "form": {},
        },
    )


@router.post("/setup/welcome", response_class=HTMLResponse)
async def setup_welcome_post(db: DbSession) -> Response:
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("welcome")
    return _redirect("/setup/admin_account")


@router.post("/setup/admin", response_class=HTMLResponse)
async def setup_admin_post(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    try:
        await auth_svc.create_admin(username, password)
    except AuthenticationError as exc:
        return templates.TemplateResponse(
            request,
            "setup_wizard.html",
            {
                "step": "admin_account",
                "steps": WIZARD_STEPS,
                "step_index": WIZARD_STEPS.index("admin_account"),
                "total_steps": len(WIZARD_STEPS),
                "error": str(exc),
                "form": {"username": username},
            },
            status_code=422,
        )
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("admin_account")

    # Auto-login so the session cookie is set before the network step,
    # which needs auth to fetch /api/system/interfaces.
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session = await auth_svc.login(username=username, password=password, ip=ip, user_agent=ua)
    resp = _redirect("/setup/network")
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_LIFETIME_HOURS * 3600,
    )
    return resp


@router.post("/setup/network", response_class=HTMLResponse)
async def setup_network_post(
    db: DbSession,
    wake_interface: Annotated[str, Form()] = "",
    default_wake_strategy: Annotated[str, Form()] = "etherwake",
    default_poll_timeout_s: Annotated[int, Form()] = 120,
) -> Response:
    settings_svc = SettingsService(SqlSettingsRepository(db))
    await settings_svc.set("wake_interface", wake_interface)
    await settings_svc.set("default_wake_strategy", default_wake_strategy)
    await settings_svc.set("default_poll_timeout_s", default_poll_timeout_s)
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("network")
    return _redirect("/setup/first_machine")


@router.post("/setup/{step}/back", response_class=HTMLResponse)
async def setup_back(step: str, db: DbSession) -> Response:
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    prev = await setup_svc.go_back(step)
    return _redirect(f"/setup/{prev}")


@router.post("/setup/skip_machine", response_class=HTMLResponse)
async def setup_skip_machine(db: DbSession) -> Response:
    setup_svc = SetupStateService(SqlSetupStateRepository(db))
    await setup_svc.advance("first_machine")
    await setup_svc.advance("complete")
    return _redirect("/setup/complete")


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/auth/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    response: Response,
    db: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    try:
        session = await auth_svc.login(username=username, password=password, ip=ip, user_agent=ua)
    except AuthenticationError:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password.", "username": username},
            status_code=401,
        )
    resp = _redirect("/machines")
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_LIFETIME_HOURS * 3600,
    )
    return resp


@router.post("/auth/logout", response_class=HTMLResponse)
async def logout_post(request: Request, db: DbSession) -> Response:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        auth_svc = get_auth_service(
            user_repo=SqlUserRepository(db),
            session_repo=SqlSessionRepository(db),
            token_repo=SqlApiTokenRepository(db),
        )
        from contextlib import suppress

        with suppress(Exception):
            await auth_svc.logout(session_id)
    resp = _redirect("/login")
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------------
# Machines pages (session-gated)
# ---------------------------------------------------------------------------
async def _require_web_auth(request: Request, db: AsyncSession):  # type: ignore[no-untyped-def]
    """Return (session, user) or redirect to login."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None, None
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    try:
        return await auth_svc.validate_session(session_id)
    except Exception:
        return None, None


@router.get("/machines", response_class=HTMLResponse)
async def machines_page(request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    repo = SqlMachineRepository(db)
    machines = await repo.list_all()
    csrf = await _get_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "machines.html",
        {"machines": machines, "user": user, "csrf_token": csrf},
    )


@router.get("/machines/new", response_class=HTMLResponse)
async def machine_new_page(request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    csrf = await _get_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "machine_form.html",
        {"machine": None, "csrf_token": csrf},
    )


@router.post("/machines/new", response_class=HTMLResponse)
async def machine_new_post(
    request: Request,
    db: DbSession,
    name: Annotated[str, Form()] = "",
    ip_address: Annotated[str, Form()] = "",
    mac_address: Annotated[str, Form()] = "",
    ssh_port: Annotated[int, Form()] = 22,
    hostname: Annotated[str, Form()] = "",
    wake_interface: Annotated[str, Form()] = "",
    wake_strategy: Annotated[str, Form()] = "etherwake",
    broadcast_address: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    csrf = await _get_csrf(request, db)
    repo = SqlMachineRepository(db)
    try:
        await repo.create(
            name=name,
            ip_address=ip_address,
            mac_address=mac_address,
            ssh_port=ssh_port,
            hostname=hostname or None,
            wake_interface=wake_interface or None,
            wake_strategy=wake_strategy,
            broadcast_address=broadcast_address or None,
            enabled=enabled == "1",
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "machine_form.html",
            {"machine": None, "csrf_token": csrf, "error": str(exc)},
            status_code=422,
        )
    from_setup = request.query_params.get("from") == "setup"
    if from_setup:
        setup_svc = SetupStateService(SqlSetupStateRepository(db))
        await setup_svc.advance("first_machine")
        await setup_svc.advance("complete")
        return _redirect("/setup/complete")
    return _redirect("/machines")


@router.get("/machines/{machine_id}/edit", response_class=HTMLResponse)
async def machine_edit_page(machine_id: str, request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    repo = SqlMachineRepository(db)
    machine = await repo.get_by_id(machine_id)
    if machine is None:
        return _redirect("/machines")
    csrf = await _get_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "machine_form.html",
        {"machine": machine, "csrf_token": csrf},
    )


@router.post("/machines/{machine_id}/edit", response_class=HTMLResponse)
async def machine_edit_post(
    machine_id: str,
    request: Request,
    db: DbSession,
    name: Annotated[str, Form()] = "",
    ip_address: Annotated[str, Form()] = "",
    mac_address: Annotated[str, Form()] = "",
    ssh_port: Annotated[int, Form()] = 22,
    hostname: Annotated[str, Form()] = "",
    wake_interface: Annotated[str, Form()] = "",
    wake_strategy: Annotated[str, Form()] = "etherwake",
    broadcast_address: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    repo = SqlMachineRepository(db)
    csrf = await _get_csrf(request, db)
    try:
        updated = await repo.update(
            machine_id,
            name=name,
            ip_address=ip_address,
            mac_address=mac_address,
            ssh_port=ssh_port,
            hostname=hostname or None,
            wake_interface=wake_interface or None,
            wake_strategy=wake_strategy,
            broadcast_address=broadcast_address or None,
            enabled=enabled == "1",
        )
        if updated is None:
            return _redirect("/machines")
    except Exception as exc:
        machine = await repo.get_by_id(machine_id)
        return templates.TemplateResponse(
            request,
            "machine_form.html",
            {"machine": machine, "csrf_token": csrf, "error": str(exc)},
            status_code=422,
        )
    return _redirect("/machines")


# ---------------------------------------------------------------------------
# Token management page
# ---------------------------------------------------------------------------
@router.get("/tokens", response_class=HTMLResponse)
async def tokens_page(request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    machines = await SqlMachineRepository(db).list_all()
    csrf = await _get_csrf(request, db)
    # Fetch active tokens and group by machine_id
    auth_svc = get_auth_service(
        user_repo=SqlUserRepository(db),
        session_repo=SqlSessionRepository(db),
        token_repo=SqlApiTokenRepository(db),
    )
    all_tokens = await auth_svc.list_api_tokens()
    # Build machine_id -> token list map; None key = global tokens
    tokens_by_machine: dict[str | None, list[object]] = {}
    for t in all_tokens:
        tokens_by_machine.setdefault(t.machine_id, []).append(t)

    return templates.TemplateResponse(
        request,
        "tokens.html",
        {
            "machines": machines,
            "tokens_by_machine": tokens_by_machine,
            "csrf_token": csrf,
        },
    )


# ---------------------------------------------------------------------------
# SSH Auto-Wake setup guide
# ---------------------------------------------------------------------------
@router.get("/ssh-setup", response_class=HTMLResponse)
async def ssh_setup_page(request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    machines = await SqlMachineRepository(db).list_all()
    csrf = await _get_csrf(request, db)
    # Derive the public base URL from the incoming request
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "ssh_setup.html",
        {
            "machines": machines,
            "csrf_token": csrf,
            "base_url": base_url,
        },
    )


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: DbSession) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    svc = SettingsService(SqlSettingsRepository(db))
    settings = await svc.get_all()
    csrf = await _get_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "csrf_token": csrf, "saved": False},
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    db: DbSession,
    wake_interface: Annotated[str, Form()] = "",
    default_wake_strategy: Annotated[str, Form()] = "etherwake",
    default_poll_timeout_s: Annotated[int, Form()] = 120,
    allow_api_tokens: Annotated[str, Form()] = "",
    session_lifetime_hours: Annotated[int, Form()] = 12,
) -> Response:
    _session, user = await _require_web_auth(request, db)
    if user is None:
        return _redirect("/login")
    svc = SettingsService(SqlSettingsRepository(db))
    await svc.set("wake_interface", wake_interface)
    await svc.set("default_wake_strategy", default_wake_strategy)
    await svc.set("default_poll_timeout_s", default_poll_timeout_s)
    await svc.set("allow_api_tokens", allow_api_tokens == "1")
    await svc.set("session_lifetime_hours", session_lifetime_hours)
    settings = await svc.get_all()
    csrf = await _get_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "csrf_token": csrf, "saved": True},
    )
