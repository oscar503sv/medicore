"""Console session lifetime: absolute cap, idle timeout, throttled activity, account state."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from medicore.application.common.errors import AuthenticationFailed
from medicore.application.common.platform_session import PlatformSessionPolicy
from medicore.application.use_cases.platform import AuthenticatePlatformAdmin
from medicore.application.use_cases.platform_session import ResolvePlatformSession
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.enums import UserStatus
from medicore.domain.shared.identifiers import SessionId
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher

START = datetime(2026, 11, 14, 9, 0)
POLICY = PlatformSessionPolicy()


def _login(seed, clock, issuer=None):
    auth = AuthenticatePlatformAdmin(
        seed.factory, PlainPasswordHasher(), issuer or FakeTokenIssuer(), clock, POLICY
    )
    return auth.execute(seed.platform_admin.email, PASSWORD)


def _resolver(seed, clock) -> ResolvePlatformSession:
    return ResolvePlatformSession(seed.factory, clock, POLICY)


def _resolve(seed, clock, session_id: SessionId, **kwargs):
    return _resolver(seed, clock).execute(str(seed.platform_admin.id), session_id, **kwargs)


def _stored(seed, session_id: SessionId) -> AuthSession:
    return seed.factory.store.sessions[session_id.value]


def test_login_session_uses_platform_lifetime():
    seed = seed_clinic()
    clock = FixedClock(START)
    issuer = FakeTokenIssuer()
    dto = _login(seed, clock, issuer)

    stored = _stored(seed, dto.session_id)
    assert stored.expires_at == START + timedelta(minutes=480)
    assert stored.last_activity_at == START
    assert issuer.last_ttl_minutes == 480


def test_resolve_touches_activity_after_granularity():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    clock.set(START + timedelta(seconds=10))
    _resolve(seed, clock, dto.session_id)
    assert _stored(seed, dto.session_id).last_activity_at == START

    clock.set(START + timedelta(seconds=61))
    _resolve(seed, clock, dto.session_id)
    assert _stored(seed, dto.session_id).last_activity_at == START + timedelta(seconds=61)


def test_resolve_returns_context_with_session_and_network_data():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    ctx = _resolve(seed, clock, dto.session_id, ip_address="10.0.0.1", user_agent="ua")

    assert ctx.admin_id == seed.platform_admin.id
    assert ctx.session_id == dto.session_id
    assert (ctx.ip_address, ctx.user_agent) == ("10.0.0.1", "ua")


def test_background_request_does_not_touch():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    clock.set(START + timedelta(minutes=5))
    _resolve(seed, clock, dto.session_id, background=True)

    assert _stored(seed, dto.session_id).last_activity_at == START


def test_idle_timeout_revokes_and_raises():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    clock.set(START + timedelta(minutes=30))
    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, clock, dto.session_id)

    assert exc.value.code == "auth.session_idle_timeout"
    assert _stored(seed, dto.session_id).revoked_at == clock.now()


def test_background_polling_alone_lets_the_session_go_idle():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    for minutes in (10, 20, 29):
        clock.set(START + timedelta(minutes=minutes))
        _resolve(seed, clock, dto.session_id, background=True)
    clock.set(START + timedelta(minutes=31))
    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, clock, dto.session_id, background=True)
    assert exc.value.code == "auth.session_idle_timeout"


def test_activity_keeps_session_alive_until_absolute_cap():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    for minutes in range(20, 480, 20):
        clock.set(START + timedelta(minutes=minutes))
        _resolve(seed, clock, dto.session_id)

    clock.set(START + timedelta(minutes=480))
    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, clock, dto.session_id)
    assert exc.value.code == "auth.session_expired"


def test_inactive_admin_rejected_and_session_revoked():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)
    seed.platform_admin.status = UserStatus.SUSPENDED

    clock.set(START + timedelta(minutes=1))
    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, clock, dto.session_id)

    assert exc.value.code == "auth.account_inactive"
    assert _stored(seed, dto.session_id).revoked_at is not None


def test_revoked_session_is_rejected():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)
    _stored(seed, dto.session_id).revoke(clock.now())

    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, clock, dto.session_id)
    assert exc.value.code == "auth.session_expired"


def test_unknown_session_is_rejected():
    seed = seed_clinic()
    with pytest.raises(AuthenticationFailed) as exc:
        _resolve(seed, FixedClock(START), SessionId.new())
    assert exc.value.code == "auth.session_expired"


def test_session_of_other_scope_or_user_rejected():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)

    tenant_session = _stored(seed, dto.session_id)
    tenant_session.scope = "tenant"
    with pytest.raises(AuthenticationFailed) as scope_exc:
        _resolve(seed, clock, dto.session_id)
    assert scope_exc.value.code == "auth.session_expired"

    tenant_session.scope = "platform"
    with pytest.raises(AuthenticationFailed) as user_exc:
        _resolver(seed, clock).execute(str(seed.admin.id), dto.session_id)
    assert user_exc.value.code == "auth.session_expired"


def test_malformed_admin_id_is_rejected_as_expired():
    seed = seed_clinic()
    clock = FixedClock(START)
    dto = _login(seed, clock)
    with pytest.raises(AuthenticationFailed) as exc:
        _resolver(seed, clock).execute("not-a-uuid", dto.session_id)
    assert exc.value.code == "auth.session_expired"
