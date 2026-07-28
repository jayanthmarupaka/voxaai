"""Application settings, loaded once from the environment.

Everything secret lives here and nowhere else — no module reads ``os.environ``
directly. The root ``.env`` is shared with the web app so there is a single
place to configure the whole stack.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/config.py -> apps/api/app -> apps/api -> apps -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Database --------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voxa"

    # -- Azure OpenAI ----------------------------------------------------------
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4.1"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # -- Clerk -----------------------------------------------------------------
    clerk_secret_key: str = ""
    clerk_issuer: str = ""
    clerk_webhook_secret: str = ""

    # -- Google Calendar -------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/integrations/google/callback"

    # -- Crypto ----------------------------------------------------------------
    token_encryption_key: str = ""

    # -- Email -----------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Voxa"

    # -- Speech ----------------------------------------------------------------
    whisper_model: str = "base.en"
    whisper_compute_type: str = "int8"
    piper_voice: str = "en_US-lessac-medium"
    voice_models_dir: str = "./models"

    # -- URLs ------------------------------------------------------------------
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    # -- Behaviour toggles -----------------------------------------------------
    # When true, unauthenticated requests are rejected outright rather than
    # falling back to anything. There is deliberately no "dev bypass" here:
    # tenancy always comes from a verified Clerk token.
    debug: bool = False

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Accept the plain ``postgresql://`` URLs that Neon/Render hand out.

        asyncpg also chokes on libpq-only query parameters (``sslmode``,
        ``channel_binding``), so those are stripped here; TLS is configured
        explicitly in ``app.db`` instead.
        """
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql://", 1)
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

        base, _, query = value.partition("?")
        if not query:
            return value
        keep = [
            part
            for part in query.split("&")
            if part.split("=", 1)[0] not in {"sslmode", "channel_binding", "ssl"}
        ]
        return f"{base}?{'&'.join(keep)}" if keep else base

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def models_path(self) -> Path:
        path = Path(self.voice_models_dir)
        if not path.is_absolute():
            path = REPO_ROOT / "apps" / "api" / path
        return path

    @property
    def sync_database_url(self) -> str:
        """Alembic runs synchronously; hand it a psycopg-free sync-style URL."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["REPO_ROOT", "Settings", "get_settings", "settings"]
