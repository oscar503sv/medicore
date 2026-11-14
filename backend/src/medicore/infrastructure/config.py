"""Infrastructure configuration read from environment variables / .env file."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets that must never reach production (the dev default + the .env.example placeholder).
_INSECURE_SECRETS = {
    "",
    "change-me",
    "cambia-esto-en-produccion-usa-openssl-rand-hex-32",
}

_MFA_KEY_BYTES = 32

TrustedNetworks = tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]


@lru_cache
def _parse_networks(spec: str) -> TrustedNetworks:
    """Parse a comma-separated list of IPs/CIDRs (e.g. "127.0.0.1, 10.0.0.0/8")."""
    networks = []
    for value in spec.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            raise ValueError(
                f"TRUSTED_PROXIES contains an invalid IP or CIDR: {value!r}"
            ) from exc
    return tuple(networks)


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
    # Reverse proxies whose X-Forwarded-For we honor (comma-separated IPs/CIDRs).
    # Empty (default) means the header is ignored and the socket peer is the client IP.
    trusted_proxies: str = ""
    # Deployed git commit, shown in the platform console (Coolify can inject SOURCE_COMMIT).
    source_commit: str = ""
    # Secure flag (and __Host-/__Secure- cookie prefixes). None = derived from the environment:
    # on everywhere except development, which runs on plain http://localhost.
    cookie_secure: bool | None = None
    # Superadmin console: idle timeout and absolute cap, much stricter than the clinic app.
    platform_session_idle_minutes: int = 30
    platform_session_max_minutes: int = 480
    # Path of the console session cookie: it is only sent to the platform API.
    platform_cookie_path: str = "/api/v1/platform"
    # Superadmin second factor. The key encrypts the TOTP secrets at rest (32 bytes, base64url);
    # mandatory in production, derived from JWT_SECRET in development when left empty.
    mfa_encryption_key: str = ""
    mfa_issuer: str = "Medicore"  # name shown in the authenticator app

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment.strip().lower() != "development"

    @property
    def mfa_key_bytes(self) -> bytes:
        value = self.mfa_encryption_key.strip()
        if not value:
            # Development only (production refuses to start without a key): a stable key
            # that is not the JWT secret itself.
            return hmac.new(
                self.jwt_secret.encode(), b"medicore.mfa.dev-only", hashlib.sha256
            ).digest()
        try:
            key = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("MFA_ENCRYPTION_KEY is not valid base64url.") from exc
        if len(key) != _MFA_KEY_BYTES:
            raise ValueError(f"MFA_ENCRYPTION_KEY must decode to {_MFA_KEY_BYTES} bytes.")
        return key

    @property
    def cors_origins_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [o.strip() for o in value.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(self) -> TrustedNetworks:
        return _parse_networks(self.trusted_proxies)

    @model_validator(mode="after")
    def _validate_trusted_proxies(self) -> Settings:
        # Fail fast on a typo'd CIDR rather than silently distrusting the proxy.
        _parse_networks(self.trusted_proxies)
        return self

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

    @model_validator(mode="after")
    def _enforce_production_cors(self) -> Settings:
        # Fail fast rather than serve a production API open to any origin.
        if self.is_production and self.cors_origins.strip() == "*":
            raise ValueError(
                "CORS_ORIGINS cannot be '*' in production — list the frontend "
                "origins explicitly (e.g. https://app.example.com)."
            )
        return self

    @model_validator(mode="after")
    def _validate_platform_session(self) -> Settings:
        if not 5 <= self.platform_session_idle_minutes <= self.platform_session_max_minutes:
            raise ValueError(
                "PLATFORM_SESSION_IDLE_MINUTES must be at least 5 and not exceed "
                "PLATFORM_SESSION_MAX_MINUTES."
            )
        return self

    @model_validator(mode="after")
    def _enforce_secure_cookies_in_production(self) -> Settings:
        # Without Secure the session cookies would travel over plain http.
        if self.is_production and self.cookie_secure is False:
            raise ValueError("COOKIE_SECURE cannot be false in production.")
        return self

    @model_validator(mode="after")
    def _validate_mfa_key(self) -> Settings:
        if self.is_production and not self.mfa_encryption_key.strip():
            raise ValueError(
                "MFA_ENCRYPTION_KEY must be set in production (32 bytes, base64url; see "
                ".env.example for the command that generates one)."
            )
        if self.mfa_encryption_key.strip():
            _ = self.mfa_key_bytes  # raises on a malformed key, failing fast at startup
        return self

    @model_validator(mode="after")
    def _default_docs_off_in_production(self) -> Settings:
        # Docs stay available in production only as an explicit opt-in.
        if self.is_production and "enable_docs" not in self.model_fields_set:
            self.enable_docs = False
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
