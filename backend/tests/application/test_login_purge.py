"""Stale failed-login entries are purged on successful logins."""

from __future__ import annotations

from datetime import datetime, timedelta

from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher

NOW = datetime(2026, 6, 11, 9, 0)


def test_successful_login_purges_stale_entries_only():
    seed = seed_clinic()
    attempts = seed.factory.store.login_attempts
    attempts["tenant:x:old@x.test"] = (2, NOW - timedelta(hours=2), None)
    attempts["tenant:x:recent@x.test"] = (2, NOW - timedelta(minutes=5), None)
    attempts["tenant:x:locked@x.test"] = (9, NOW - timedelta(hours=2), NOW + timedelta(minutes=1))

    login = AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock(NOW)
    )
    login.execute(
        AuthenticateUserCommand(
            slug=str(seed.tenant.slug), email=seed.doctor.email, password=PASSWORD
        )
    )

    assert set(attempts) == {"tenant:x:recent@x.test", "tenant:x:locked@x.test"}
