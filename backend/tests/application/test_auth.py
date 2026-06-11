"""Tests for AuthenticateUser and preference use cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from medicore.application.common.errors import AuthenticationFailed, TooManyLoginAttempts
from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    ChangePassword,
    GetMyProfile,
    SwitchTheme,
    UpdateMyProfile,
)
from medicore.domain.enums import Role, ThemePref, UserStatus
from medicore.domain.shared.identifiers import SessionId
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


def _session_id(token: str) -> SessionId:
    return SessionId.parse(FakeTokenIssuer().decode(token).session_id)


def test_login_creates_active_session_row():
    seed = seed_clinic()
    clock = FixedClock()
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), clock)

    session = auth.execute(
        AuthenticateUserCommand(slug="clinica-norte", email=seed.doctor.email, password=PASSWORD)
    )

    stored = seed.factory.store.sessions[_session_id(session.token).value]
    assert stored.is_active(clock.now())
    assert stored.scope == "tenant"
    assert stored.user_id == seed.doctor.id.value
    assert stored.expires_at == clock.now() + timedelta(minutes=1440)


def test_change_password_revokes_other_sessions_but_keeps_current():
    seed = seed_clinic()
    clock = FixedClock()
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), clock)
    cmd = AuthenticateUserCommand(
        slug="clinica-norte", email=seed.doctor.email, password=PASSWORD
    )
    old_sid = _session_id(auth.execute(cmd).token)
    current_sid = _session_id(auth.execute(cmd).token)

    actor = replace(seed.doctor_actor, session_id=current_sid)
    ChangePassword(seed.factory, PlainPasswordHasher(), clock).execute(
        actor, PASSWORD, "nueva-clave-123"
    )

    sessions = seed.factory.store.sessions
    assert not sessions[old_sid.value].is_active(clock.now())
    assert sessions[current_sid.value].is_active(clock.now())


def _login_cmd(email: str, password: str) -> AuthenticateUserCommand:
    return AuthenticateUserCommand(slug="clinica-norte", email=email, password=password)


def _fail_login(auth, email: str) -> None:
    with pytest.raises(AuthenticationFailed):
        auth.execute(_login_cmd(email, "wrong-password"))


def test_lockout_after_five_failures_blocks_even_correct_password():
    seed = seed_clinic()
    auth = make_auth(seed)
    for _ in range(5):
        _fail_login(auth, seed.doctor.email)

    with pytest.raises(TooManyLoginAttempts):
        auth.execute(_login_cmd(seed.doctor.email, PASSWORD))
    # engaging the lockout on an existing account is audited
    uow = seed.factory.for_tenant(seed.tenant.id)
    assert uow.audit.query(action="auth.login_locked")


def test_lockout_also_applies_to_unknown_accounts():
    # Anti-enumeration: a non-existent account locks exactly like a real one.
    seed = seed_clinic()
    auth = make_auth(seed)
    for _ in range(5):
        _fail_login(auth, "nadie@example.com")

    with pytest.raises(TooManyLoginAttempts):
        auth.execute(_login_cmd("nadie@example.com", "whatever"))


def test_successful_login_resets_failure_count():
    seed = seed_clinic()
    auth = make_auth(seed)
    for _ in range(4):
        _fail_login(auth, seed.doctor.email)
    auth.execute(_login_cmd(seed.doctor.email, PASSWORD))

    for _ in range(4):
        _fail_login(auth, seed.doctor.email)
    # still not locked: the success cleared the earlier failures
    session = auth.execute(_login_cmd(seed.doctor.email, PASSWORD))
    assert session.user_id == seed.doctor.id


def test_lockout_expires_and_backoff_doubles():
    seed = seed_clinic()
    clock = FixedClock()
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), clock)
    start = clock.now()

    for _ in range(5):
        _fail_login(auth, seed.doctor.email)  # 5th failure → locked for 1 min
    with pytest.raises(TooManyLoginAttempts):
        auth.execute(_login_cmd(seed.doctor.email, PASSWORD))

    clock.set(start + timedelta(seconds=61))  # first lockout expired
    _fail_login(auth, seed.doctor.email)  # 6th failure → locked for 2 min

    clock.set(start + timedelta(seconds=61 + 90))  # 1.5 min later: still locked
    with pytest.raises(TooManyLoginAttempts):
        auth.execute(_login_cmd(seed.doctor.email, PASSWORD))

    clock.set(start + timedelta(seconds=61 + 121))  # past the 2 min: attempts run again
    _fail_login(auth, seed.doctor.email)


def test_failures_outside_window_restart_the_count():
    seed = seed_clinic()
    clock = FixedClock()
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), clock)
    start = clock.now()

    for _ in range(4):
        _fail_login(auth, seed.doctor.email)
    clock.set(start + timedelta(minutes=16))  # the four failures fall out of the window
    for _ in range(4):
        _fail_login(auth, seed.doctor.email)

    session = auth.execute(_login_cmd(seed.doctor.email, PASSWORD))
    assert session.user_id == seed.doctor.id


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
