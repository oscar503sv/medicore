"""TTL regression tests for JwtTokenIssuer.

Support (impersonation) sessions — those carrying an ``impersonator`` claim — must
expire sooner than regular sessions. The fake issuer doesn't encode expiry, so this
exercises the real PyJWT-backed issuer and inspects the ``exp``/``iat`` distance.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from medicore.application.ports.token_issuer import SessionClaims
from medicore.infrastructure.auth.jwt_token_issuer import JwtTokenIssuer
from medicore.infrastructure.config import get_settings

_SECRET = "test-secret-at-least-32-bytes-long!!"


def _ttl(token: str) -> timedelta:
    payload = jwt.decode(
        token, _SECRET, algorithms=["HS256"], options={"verify_exp": False, "verify_aud": False}
    )
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


def test_session_id_claim_round_trips(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    get_settings.cache_clear()
    try:
        issuer = JwtTokenIssuer()
        token = issuer.issue(
            SessionClaims(user_id="u", tenant_id="t", role="admin", session_id="sid-123")
        )
        assert issuer.decode(token).session_id == "sid-123"
        # a token issued without a session cannot be decoded at all
        legacy = issuer.issue(SessionClaims(user_id="u", tenant_id="t", role="admin"))
        with pytest.raises(jwt.MissingRequiredClaimError):
            issuer.decode(legacy)
    finally:
        get_settings.cache_clear()


def test_explicit_ttl_overrides_the_default(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "1440")
    get_settings.cache_clear()
    try:
        token = JwtTokenIssuer().issue(
            SessionClaims(user_id="u", scope="platform", session_id="s"), ttl_minutes=30
        )
        assert _ttl(token) == timedelta(minutes=30)
    finally:
        get_settings.cache_clear()


@pytest.fixture
def issuer(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    get_settings.cache_clear()
    yield JwtTokenIssuer()
    get_settings.cache_clear()


def _token(issuer: JwtTokenIssuer, scope: str) -> str:
    return issuer.issue(SessionClaims(user_id="u", scope=scope, session_id="s"))


@pytest.mark.parametrize("scope", ["tenant", "platform", "mfa"])
def test_each_scope_gets_its_own_audience(issuer, scope):
    payload = jwt.decode(
        _token(issuer, scope), _SECRET, algorithms=["HS256"], options={"verify_aud": False}
    )

    assert payload["aud"] == f"medicore:{scope}"


def test_token_of_another_scope_is_rejected(issuer):
    token = _token(issuer, "platform")

    with pytest.raises(jwt.InvalidAudienceError):
        issuer.decode(token, "tenant")
    assert issuer.decode(token, "tenant", "platform").scope == "platform"
    assert issuer.decode(token).scope == "platform"


def test_token_without_audience_is_rejected(issuer):
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "u", "scope": "tenant", "sid": "s", "iat": now, "exp": now + timedelta(hours=1)},
        _SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        issuer.decode(token)


def test_audience_must_match_scope(issuer):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "u", "scope": "tenant", "aud": "medicore:platform", "sid": "s",
            "iat": now, "exp": now + timedelta(hours=1),
        },
        _SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidAudienceError):
        issuer.decode(token)


def test_unlisted_algorithm_is_rejected(issuer):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "u", "scope": "tenant", "aud": "medicore:tenant", "sid": "s",
            "iat": now, "exp": now + timedelta(hours=1),
        },
        _SECRET,
        algorithm="HS512",
    )

    with pytest.raises(jwt.InvalidAlgorithmError):
        issuer.decode(token)
