"""Infrastructure configuration read from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/medicore"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    jwt_support_expire_minutes: int = 60  # TTL corta para sesiones de suplantación (soporte)


@lru_cache
def get_settings() -> Settings:
    return Settings()
