"""Application configuration, sourced from environment variables.

Defaults are chosen so the app runs locally with zero setup (SQLite),
while Railway/production supplies DATABASE_URL (Postgres) and secrets.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Avocado API"
    environment: str = "development"

    # Database. Railway injects DATABASE_URL for the Postgres plugin.
    # Falls back to a local SQLite file so the app runs anywhere.
    database_url: str = "sqlite:///./avocado.db"

    # Auth. Set SECRET_KEY in the environment so a redeploy/restart never
    # invalidates existing logins (a changed signing key = everyone gets
    # "Invalid token"). The default is stable but shared, so override it.
    secret_key: str = "dev-insecure-change-me"
    # Keep a login valid across a full working day (and across deploys): 7 days.
    access_token_expire_minutes: int = 60 * 24 * 7

    # CORS: comma-separated list of allowed origins for the web app.
    cors_origins: str = "*"

    # AI provider (optional in MVP; features degrade gracefully without it).
    ai_provider: str = "none"  # none | anthropic
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-5"

    @property
    def sqlalchemy_url(self) -> str:
        # Railway sometimes provides postgres:// which SQLAlchemy 2.x needs as
        # postgresql+psycopg://. Normalize it here.
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
