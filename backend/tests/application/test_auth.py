"""Tests for AuthenticateUser and preference use cases."""

from __future__ import annotations

import pytest

from medicore.application.common.errors import AuthenticationFailed
from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    GetMyProfile,
    SwitchTheme,
    UpdateMyProfile,
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


def test_unknown_email_still_runs_password_verification():
    # Timing-safety: verify() must run even when the email does not exist, so an
    # attacker cannot enumerate accounts by measuring response times.
    seed = seed_clinic()
    hasher = PlainPasswordHasher()
    calls: list[str] = []
    original_verify = hasher.verify
    hasher.verify = lambda plain, hashed: calls.append(plain) or original_verify(plain, hashed)
    auth = AuthenticateUser(seed.factory, hasher, FakeTokenIssuer(), FixedClock())

    with pytest.raises(AuthenticationFailed):
        auth.execute(
            AuthenticateUserCommand(
                slug="clinica-norte", email="nadie@example.com", password="whatever"
            )
        )
    assert calls == ["whatever"]


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


def test_get_my_profile_returns_user_fields():
    seed = seed_clinic()
    profile = GetMyProfile(seed.factory).execute(seed.doctor_actor)
    assert profile.name == seed.doctor.name
    assert profile.email == seed.doctor.email
    assert profile.role == Role.DOCTOR
    assert profile.specialty == seed.doctor.specialty
    assert profile.bio is None  # no DoctorProfile seeded yet


def test_update_my_profile_changes_name_and_phone():
    seed = seed_clinic()
    profile = UpdateMyProfile(seed.factory, FixedClock()).execute(
        seed.doctor_actor, name="Dra. Elena Vásquez", phone="+34 911 23 45 67"
    )
    assert profile.name == "Dra. Elena Vásquez"
    assert profile.phone == "+34 911 23 45 67"
    uow = seed.factory.for_tenant(seed.tenant.id)
    saved = uow.users.get_by_id(seed.doctor.id)
    assert saved.name == "Dra. Elena Vásquez"
    assert saved.phone == "+34 911 23 45 67"
    assert uow.audit.query(action="user.profile_updated")


def test_update_my_profile_leaves_immutable_fields_untouched():
    seed = seed_clinic()
    original_email = seed.doctor.email
    original_specialty = seed.doctor.specialty
    UpdateMyProfile(seed.factory, FixedClock()).execute(seed.doctor_actor, name="Nuevo Nombre")
    saved = seed.factory.for_tenant(seed.tenant.id).users.get_by_id(seed.doctor.id)
    assert saved.email == original_email
    assert saved.specialty == original_specialty
    assert saved.role == Role.DOCTOR


def test_update_my_profile_creates_doctor_profile_for_bio():
    seed = seed_clinic()
    profile = UpdateMyProfile(seed.factory, FixedClock()).execute(
        seed.doctor_actor, bio="Cardióloga especialista en hipertensión."
    )
    assert profile.bio == "Cardióloga especialista en hipertensión."
    uow = seed.factory.for_tenant(seed.tenant.id)
    assert uow.doctor_profiles.get_by_user_id(seed.doctor.id).bio == (
        "Cardióloga especialista en hipertensión."
    )


def test_update_my_profile_ignores_bio_for_non_doctor():
    seed = seed_clinic()
    UpdateMyProfile(seed.factory, FixedClock()).execute(
        seed.receptionist_actor, bio="should be ignored"
    )
    uow = seed.factory.for_tenant(seed.tenant.id)
    assert uow.doctor_profiles.get_by_user_id(seed.receptionist.id) is None
