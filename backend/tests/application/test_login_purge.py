"""Stale failed-login entries are purged on successful logins."""

from __future__ import annotations

from datetime import datetime, timedelta

from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher

NOW = datetime(2026, 6, 11, 9, 0)


def _sign_in(seed) -> None:
    login = AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock(NOW)
    )
    login.execute(
        AuthenticateUserCommand(
            slug=str(seed.tenant.slug), email=seed.doctor.email, password=PASSWORD
        )
    )


def test_successful_login_purges_stale_entries_only():
    seed = seed_clinic()
    attempts = seed.factory.store.login_attempts
    attempts["tenant:x:old@x.test"] = (2, NOW - timedelta(hours=2), None)
    attempts["tenant:x:recent@x.test"] = (2, NOW - timedelta(minutes=5), None)
    attempts["tenant:x:locked@x.test"] = (9, NOW - timedelta(hours=2), NOW + timedelta(minutes=1))

    _sign_in(seed)

    assert "tenant:x:old@x.test" not in attempts
    assert {"tenant:x:recent@x.test", "tenant:x:locked@x.test"} <= set(attempts)


def test_pair_with_a_recent_success_is_kept_and_an_old_one_is_purged():
    seed = seed_clinic()
    attempts = seed.factory.store.login_attempts
    successes = seed.factory.store.login_successes
    recent_pair = "tenant:x:a@x.test|203.0.113.9"
    old_pair = "tenant:x:b@x.test|203.0.113.9"
    for ident, days in ((recent_pair, 10), (old_pair, 31)):
        attempts[ident] = (0, NOW - timedelta(hours=2), None)
        successes[ident] = NOW - timedelta(days=days)

    _sign_in(seed)

    assert recent_pair in attempts
    assert old_pair not in attempts
    assert old_pair not in successes
