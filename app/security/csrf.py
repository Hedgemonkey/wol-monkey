"""CSRF token generation and validation using itsdangerous."""

import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings

_CSRF_SALT = "wol-monkey-csrf"
_MAX_AGE = 3600  # 1 hour


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().app_secret)


def generate_csrf_secret() -> str:
    """Generate a per-session CSRF secret (stored in the session row)."""
    return secrets.token_hex(32)


def generate_csrf_token(session_id: str, csrf_secret: str) -> str:
    """Generate a signed CSRF token tied to a session."""
    s = _get_serializer()
    return s.dumps({"sid": session_id, "sec": csrf_secret}, salt=_CSRF_SALT)


def validate_csrf_token(token: str, session_id: str, csrf_secret: str) -> bool:
    """Return True if the CSRF token is valid and not expired."""
    s = _get_serializer()
    try:
        data = s.loads(token, salt=_CSRF_SALT, max_age=_MAX_AGE)
        return bool(data.get("sid") == session_id and data.get("sec") == csrf_secret)
    except (BadSignature, Exception):
        return False
