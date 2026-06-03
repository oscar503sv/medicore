"""JWT-backed TokenIssuer using PyJWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from medicore.application.ports.token_issuer import SessionClaims
from medicore.infrastructure.config import get_settings


class JwtTokenIssuer:
    def __init__(self) -> None:
        cfg = get_settings()
        self._secret = cfg.jwt_secret
        self._algorithm = cfg.jwt_algorithm
        self._expire_minutes = cfg.jwt_expire_minutes

    def issue(self, claims: SessionClaims) -> str:
        payload = {
            "sub": claims.user_id,
            "tenant": claims.tenant_id,
            "role": claims.role,
            "scope": claims.scope,
            "imp": claims.impersonator,
            "exp": datetime.now(UTC) + timedelta(minutes=self._expire_minutes),
            "iat": datetime.now(UTC),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> SessionClaims:
        payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        return SessionClaims(
            user_id=payload["sub"],
            tenant_id=payload.get("tenant"),
            role=payload.get("role", ""),
            scope=payload.get("scope", "tenant"),
            impersonator=payload.get("imp"),
        )
