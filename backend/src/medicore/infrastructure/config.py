"""Infrastructure configuration read from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets that must never reach production (the dev default + the .env.example placeholder).
_INSECURE_SECRETS = {
    "",
    "change-me",
    "cambia-esto-en-produccion-usa-openssl-rand-hex-32",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://localhost/medicore"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    jwt_support_expire_minutes: int = 60  # TTL corta para sesiones de suplantación (soporte)
    # CORS: comma-separated origins, or "*" for any (dev default). With explicit origins,
    # credentials are allowed; with "*" they must be disabled per the CORS spec.
    cors_origins: str = "*"
    # Expose Swagger/OpenAPI docs. Consider disabling in production.
    enable_docs: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [o.strip() for o in value.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_production_secret(self) -> Settings:
        # Fail fast rather than ship a guessable JWT secret to production.
        if self.is_production and (
            self.jwt_secret in _INSECURE_SECRETS or len(self.jwt_secret) < 16
        ):
            raise ValueError(
                "JWT_SECRET must be set to a strong secret in production "
                "(e.g. `openssl rand -hex 32`)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
