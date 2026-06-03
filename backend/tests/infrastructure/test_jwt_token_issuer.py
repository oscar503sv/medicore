"""TTL regression tests for JwtTokenIssuer.

Support (impersonation) sessions — those carrying an ``impersonator`` claim — must
expire sooner than regular sessions. The fake issuer doesn't encode expiry, so this
exercises the real PyJWT-backed issuer and inspects the ``exp``/``iat`` distance.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import jwt

from medicore.application.ports.token_issuer import SessionClaims
from medicore.infrastructure.auth.jwt_token_issuer import JwtTokenIssuer
from medicore.infrastructure.config import get_settings

_SECRET = "test-secret-at-least-32-bytes-long!!"


def _ttl(token: str) -> timedelta:
    payload = jwt.decode(token, _SECRET, algorithms=["HS256"], options={"verify_exp": False})
    return datetime.fromtimestamp(payload["exp"]) - datetime.fromtimestamp(payload["iat"])


def test_support_session_has_shorter_ttl(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "1440")
    monkeypatch.setenv("JWT_SUPPORT_EXPIRE_MINUTES", "60")
    get_settings.cache_clear()
    try:
        issuer = JwtTokenIssuer()
        normal = issuer.issue(SessionClaims(user_id="u", tenant_id="t", role="admin"))
        support = issuer.issue(
            SessionClaims(user_id="u", tenant_id="t", role="admin", impersonator="a")
        )

        assert _ttl(normal) == timedelta(minutes=1440)
        assert _ttl(support) == timedelta(minutes=60)
    finally:
        get_settings.cache_clear()
