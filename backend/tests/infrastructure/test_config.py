"""Production guardrails of Settings (fail fast on insecure configuration)."""

from __future__ import annotations

import base64

import pytest

from medicore.infrastructure.config import Settings

STRONG_SECRET = "x" * 32
MFA_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps the test independent from the developer's local .env.
    return Settings(_env_file=None, **overrides)


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        make_settings(environment="production", jwt_secret=STRONG_SECRET, cors_origins="*")


def test_production_accepts_explicit_origins():
    settings = make_settings(
        environment="production",
        jwt_secret=STRONG_SECRET,
        mfa_encryption_key=MFA_KEY,
        cors_origins="https://app.example.com, https://admin.example.com",
    )
    assert settings.cors_origins_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_production_disables_docs_by_default():
    settings = make_settings(
        environment="production",
        jwt_secret=STRONG_SECRET,
        mfa_encryption_key=MFA_KEY,
        cors_origins="https://a.example",
    )
    assert settings.enable_docs is False


def test_production_respects_explicit_docs_opt_in():
    settings = make_settings(
        environment="production",
        jwt_secret=STRONG_SECRET,
        mfa_encryption_key=MFA_KEY,
        cors_origins="https://a.example",
        enable_docs=True,
    )
    assert settings.enable_docs is True


def test_production_rejects_weak_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        make_settings(
            environment="production", jwt_secret="change-me", cors_origins="https://a.example"
        )


def test_development_keeps_permissive_defaults():
    settings = make_settings()
    assert settings.cors_origins == "*"
    assert settings.enable_docs is True


def test_production_rejects_insecure_cookies():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        make_settings(
            environment="production",
            jwt_secret=STRONG_SECRET,
            cors_origins="https://a.example",
            cookie_secure=False,
        )


def test_production_cookies_are_secure_by_default():
    settings = make_settings(
        environment="production",
        jwt_secret=STRONG_SECRET,
        mfa_encryption_key=MFA_KEY,
        cors_origins="https://a.example",
    )
    assert settings.secure_cookies is True


def test_staging_cookies_are_secure_by_default():
    assert make_settings(environment="staging").secure_cookies is True


def test_development_cookies_are_not_secure_by_default():
    assert make_settings(environment="development").secure_cookies is False


def test_cookie_secure_can_be_forced_outside_production():
    assert make_settings(environment="development", cookie_secure=True).secure_cookies is True


def test_platform_idle_cannot_exceed_the_absolute_cap():
    with pytest.raises(ValueError, match="PLATFORM_SESSION_IDLE_MINUTES"):
        make_settings(platform_session_idle_minutes=60, platform_session_max_minutes=30)


def test_platform_idle_has_a_floor():
    with pytest.raises(ValueError, match="PLATFORM_SESSION_IDLE_MINUTES"):
        make_settings(platform_session_idle_minutes=4)


def test_platform_session_defaults():
    settings = make_settings()
    assert (settings.platform_session_idle_minutes, settings.platform_session_max_minutes) == (
        30,
        480,
    )
    assert settings.platform_cookie_path == "/api/v1/platform"


def _production(**overrides) -> Settings:
    return make_settings(
        environment="production",
        jwt_secret=STRONG_SECRET,
        cors_origins="https://a.example",
        **overrides,
    )


def test_production_requires_the_mfa_key():
    with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY"):
        _production()


@pytest.mark.parametrize("key", ["c2hvcnQ", "!!!not-base64!!!", MFA_KEY[:-4]])
def test_mfa_key_must_decode_to_32_bytes(key):
    with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY"):
        _production(mfa_encryption_key=key)


def test_mfa_key_is_decoded_from_base64url():
    assert _production(mfa_encryption_key=MFA_KEY).mfa_key_bytes == bytes(range(32))


def test_development_derives_a_stable_mfa_key_from_the_jwt_secret():
    first = make_settings(jwt_secret="a" * 32).mfa_key_bytes
    assert len(first) == 32
    assert first == make_settings(jwt_secret="a" * 32).mfa_key_bytes
    assert first != make_settings(jwt_secret="b" * 32).mfa_key_bytes
    assert first != b"a" * 32


def test_mfa_issuer_defaults_to_medicore():
    assert make_settings().mfa_issuer == "Medicore"
