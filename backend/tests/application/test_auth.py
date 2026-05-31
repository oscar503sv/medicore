"""Tests for AuthenticateUser and preference use cases."""

from __future__ import annotations

import pytest

from medicore.application.common.errors import AuthenticationFailed
from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    SwitchTheme,
)
from medicore.domain.enums import Role, ThemePref, UserStatus
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher


def make_auth(seed):
    return AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock()
    )


def test_authenticate_success_returns_session():
    seed = seed_clinic()
    auth = make_auth(seed)

    session = auth.execute(
        AuthenticateUserCommand(slug="clinica-norte", email=seed.doctor.email, password=PASSWORD)
    )

    assert session.user_id == seed.doctor.id
    assert session.tenant_id == seed.tenant.id
    assert session.role == Role.DOCTOR
    # decoding the token recovers the claims
    claims = FakeTokenIssuer().decode(session.token)
    assert claims.user_id == str(seed.doctor.id)
    # login is audited and last_seen recorded
    uow = seed.factory.for_tenant(seed.tenant.id)
    assert uow.users.get_by_id(seed.doctor.id).last_seen_at is not None
    assert uow.audit.query(action="auth.login")


def test_unknown_organization_fails():
    seed = seed_clinic()
    with pytest.raises(AuthenticationFailed):
        make_auth(seed).execute(
            AuthenticateUserCommand(slug="otra-clinica", email=seed.doctor.email, password=PASSWORD)
        )


def test_wrong_password_fails():
    seed = seed_clinic()
    with pytest.raises(AuthenticationFailed):
        make_auth(seed).execute(
            AuthenticateUserCommand(
                slug="clinica-norte", email=seed.doctor.email, password="nope"
            )
        )


def test_suspended_user_cannot_authenticate():
    seed = seed_clinic()
    seed.doctor.status = UserStatus.SUSPENDED
    seed.factory.store.users[seed.doctor.id.value] = seed.doctor
    with pytest.raises(AuthenticationFailed):
        make_auth(seed).execute(
            AuthenticateUserCommand(
                slug="clinica-norte", email=seed.doctor.email, password=PASSWORD
            )
        )


def test_switch_theme_persists():
    seed = seed_clinic()
    SwitchTheme(seed.factory).execute(seed.doctor_actor, ThemePref.DARK)
    uow = seed.factory.for_tenant(seed.tenant.id)
    assert uow.users.get_by_id(seed.doctor.id).preferences.theme == ThemePref.DARK
