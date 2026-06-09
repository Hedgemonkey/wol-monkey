"""GET /api/health — unauthenticated liveness endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    """Returns service liveness. No sensitive data. No authentication required."""
    return HealthResponse(status="ok", version=APP_VERSION)
