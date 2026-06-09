"""WoL-Monkey application factory."""

import logging
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.machines import router as machines_router
from app.api.setup import router as setup_router
from app.api.system import router as system_router
from app.api.wake import router as wake_router
from app.api.web import router as web_router
from app.config import get_settings

_STATIC_DIR = pathlib.Path(__file__).parent / "static"

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response


def create_app() -> FastAPI:
    settings = get_settings()

    logging.basicConfig(level=settings.log_level.upper())
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("wol_monkey_starting", version="0.1.0", debug=settings.debug)
        yield
        logger.info("wol_monkey_shutdown")

    app = FastAPI(
        title="WoL-Monkey",
        description="Secure self-hosted Wake-on-LAN control for homelab users",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Security headers on every response
    app.add_middleware(SecurityHeadersMiddleware)

    # Trusted host middleware — only accept requests for localhost (Caddy proxies externally)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "*"])

    # Routers
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(setup_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(machines_router, prefix="/api")
    app.include_router(wake_router, prefix="/api")
    app.include_router(web_router)

    # Static files (CSS / JS)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Styled error handlers
    _templates = Jinja2Templates(directory=str(pathlib.Path(__file__).parent / "templates"))

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception) -> Response:
        logger.error("unhandled_exception", path=request.url.path, error=str(exc))
        return _templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": 500, "detail": "An unexpected error occurred."},
            status_code=500,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> Response:
        if request.url.path.startswith("/api/"):
            return Response(
                content='{"detail":"Not found"}', status_code=404, media_type="application/json"
            )
        return _templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": 404, "detail": "Page not found."},
            status_code=404,
        )

    return app


app = create_app()
