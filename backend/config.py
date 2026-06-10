"""Application configuration.

Settings are read from environment variables (and an optional ``.env`` file)
via :mod:`pydantic_settings`. Access them through :func:`get_settings`, which is
cached so the ``.env`` file is parsed only once per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings sourced from the environment / ``.env``.

    Attributes:
        tmdb_api_key: Free TMDB API key. Required only for the real data
            pipeline and optional live ``/search`` enrichment; the bundled
            sample pipeline does not need it.
        database_url: SQLAlchemy database URL. Defaults to a local SQLite file.
            Swap to ``postgresql+psycopg://...`` for production with no code
            change.
        model_artifacts_path: Directory holding the model artifacts loaded at
            startup.
        cors_origins: Origins permitted to call the API (the Next.js frontend).
        auto_sample: When true, the backend generates the bundled sample
            artifacts on startup if none are found, so the server boots with
            zero data setup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    tmdb_api_key: str | None = None
    database_url: str = "sqlite:///./nextwatch.db"
    model_artifacts_path: Path = Path("./data/artifacts")
    # ``NoDecode`` stops pydantic-settings from JSON-decoding the env value so
    # the validator below can accept a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    auto_sample: bool = True

    # ---- Accounts / auth (Phase 3) ------------------------------------- #
    # HS256 signing secret for the session JWT. The default is insecure and for
    # local dev only — production MUST set JWT_SECRET to a random value.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_expire_days: int = 30
    # Send the auth cookie with the Secure flag. False for local HTTP dev; set
    # COOKIE_SECURE=true in production (HTTPS).
    cookie_secure: bool = False
    # Where the OAuth callback redirects the browser back to (the SPA origin).
    frontend_url: str = "http://localhost:3000"
    # Google OAuth client credentials (created in Google Cloud Console). Absent
    # locally → the Google sign-in routes report 503 but email/password works.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    # ---- Sign in with Apple (native iOS builds) ------------------------- #
    # The app's bundle id (and/or Services ID for web). Absent → /auth/apple
    # reports 503 but every other sign-in path works.
    apple_client_ids: Annotated[list[str], NoDecode] = []

    # ---- Transactional email (verification + password reset) ------------ #
    # SMTP host/credentials. When EMAIL_HOST is unset, outgoing mail is logged
    # to the server console instead — the dev fallback.
    email_host: str | None = None
    email_port: int = 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str = "NextWatch <no-reply@nextwatch.app>"

    # ---- Abuse protection ------------------------------------------------ #
    # Per-IP rate limiting on the auth endpoints. Disable only in tests.
    rate_limit_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Normalize Postgres URLs to the psycopg3 dialect SQLAlchemy expects.

        Render/Heroku-style ``postgres://`` (and bare ``postgresql://``, which
        SQLAlchemy would route to the absent psycopg2) both become
        ``postgresql+psycopg://``.
        """
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("cors_origins", "apple_client_ids", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow list-valued env vars to be comma-separated strings in ``.env``."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def artifacts_dir(self) -> Path:
        """Absolute path to the artifacts directory."""
        return self.model_artifacts_path.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Cached so the ``.env`` file is read once. Call ``get_settings.cache_clear()``
    in tests after mutating the environment.
    """
    return Settings()
