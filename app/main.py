"""WoL-Monkey application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.machines import router as machines_router
from app.api.setup import router as setup_router
from app.api.wake import router as wake_router
from app.config import get_settings

logger = structlog.get_logger(__name__)


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

    # Trusted host middleware (basic SSRF/host-header guard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    # Routers
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(setup_router, prefix="/api")
    app.include_router(machines_router, prefix="/api")
    app.include_router(wake_router, prefix="/api")

    return app


app = create_app()
