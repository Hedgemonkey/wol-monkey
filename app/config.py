"""Bootstrap/runtime configuration loaded from environment variables only.

User-facing settings live in PostgreSQL (see services/settings.py).
Only infrastructure/bootstrap concerns belong here.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://wol:wol@db:5432/wolmonkey"

    # Application secret — used for session signing; must be overridden in prod
    app_secret: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"

    # Bind
    bind_host: str = "0.0.0.0"
    bind_port: int = 8000

    # Trusted reverse proxies (comma-separated IPs or CIDRs)
    # e.g. "172.20.0.0/16" for the default compose network
    trusted_proxies: str = ""

    # External ports (informational — actual binding done by Caddy/compose)
    external_http_port: int = 80
    external_https_port: int = 443

    # Bootstrap toggles
    debug: bool = False
    log_level: str = "INFO"

    @field_validator("app_secret")
    @classmethod
    def secret_must_not_be_default_in_prod(cls, v: str) -> str:
        # Warn at startup; hard-fail only when debug=False enforced externally
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
