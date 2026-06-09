"""Factory helper for AuthService — avoids circular imports in dependencies."""

from app.domain.ports import ApiTokenRepository, SessionRepository, UserRepository
from app.services.auth import AuthService


def get_auth_service(
    user_repo: UserRepository,
    session_repo: SessionRepository,
    token_repo: ApiTokenRepository,
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        token_repo=token_repo,
    )
