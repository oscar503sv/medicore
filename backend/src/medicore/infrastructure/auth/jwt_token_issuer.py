"""JWT-backed TokenIssuer using PyJWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from medicore.application.ports.token_issuer import SessionClaims
from medicore.infrastructure.config import get_settings

# One audience per token type, so a token minted for one purpose (a clinic session, the
# console, a pending MFA challenge) is never accepted as another even if a check is missed.
_AUDIENCE_PREFIX = "medicore:"
_SCOPES = ("tenant", "platform", "mfa")
_REQUIRED = ["exp", "iat", "sub", "aud", "scope", "sid"]


def _audience(scope: str) -> str:
    return f"{_AUDIENCE_PREFIX}{scope}"


class JwtTokenIssuer:
    def __init__(self) -> None:
        cfg = get_settings()
        self._secret = cfg.jwt_secret
        self._algorithm = cfg.jwt_algorithm
        self._expire_minutes = cfg.jwt_expire_minutes
        self._support_expire_minutes = cfg.jwt_support_expire_minutes

    def ttl_minutes(self, impersonated: bool = False) -> int:
        # Support (impersonation) sessions expire sooner than regular ones for security.
        return self._support_expire_minutes if impersonated else self._expire_minutes

    def issue(self, claims: SessionClaims, ttl_minutes: int | None = None) -> str:
        now = datetime.now(UTC)
        expire_minutes = (
            ttl_minutes
            if ttl_minutes is not None
            else self.ttl_minutes(impersonated=claims.impersonator is not None)
        )
        payload = {
            "sub": claims.user_id,
            "tenant": claims.tenant_id,
            "role": claims.role,
            "scope": claims.scope,
            "aud": _audience(claims.scope),
            "imp": claims.impersonator,
            "sid": claims.session_id,
            "exp": now + timedelta(minutes=expire_minutes),
            "iat": now,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode(self, token: str, *scopes: str) -> SessionClaims:
        allowed = scopes or _SCOPES
        payload = jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            audience=[_audience(s) for s in allowed],
            options={"require": _REQUIRED},
        )
        if payload["aud"] != _audience(payload["scope"]):
            raise jwt.InvalidAudienceError("audience does not match the token scope")
        return SessionClaims(
            user_id=payload["sub"],
            tenant_id=payload.get("tenant"),
            role=payload.get("role", ""),
            scope=payload["scope"],
            impersonator=payload.get("imp"),
            session_id=payload.get("sid"),
        )
