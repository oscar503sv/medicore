"""Tests for the active-session use cases (listing + remote revocation)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.sessions import (
    ListMySessions,
    ListTenantSessions,
    ListUserSessions,
    RevokeAllUserSessions,
    RevokeMySession,
    RevokeTenantSession,
    RevokeUserSession,
)
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import SessionId
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher


def _login(seed, clock, email: str) -> SessionId:
    dto = AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), clock
    ).execute(AuthenticateUserCommand(slug="clinica-norte", email=email, password=PASSWORD))
    return SessionId.parse(FakeTokenIssuer().decode(dto.token).session_id)


def test_list_my_sessions_marks_the_current_one():
    seed = seed_clinic()
    clock = FixedClock()
    other_sid = _login(seed, clock, seed.doctor.email)
    current_sid = _login(seed, clock, seed.doctor.email)

    actor = replace(seed.doctor_actor, session_id=current_sid)
    sessions = ListMySessions(seed.factory.for_tenant(seed.tenant.id), clock).execute(actor)

    flags = {s.id: s.current for s in sessions}
    assert flags == {other_sid: False, current_sid: True}


def test_list_my_sessions_excludes_revoked_and_other_users():
    seed = seed_clinic()
    clock = FixedClock()
    revoked_sid = _login(seed, clock, seed.doctor.email)
    live_sid = _login(seed, clock, seed.doctor.email)
    _login(seed, clock, seed.nurse.email)  # someone else's session

    seed.factory.store.sessions[revoked_sid.value].revoke(clock.now())
    sessions = ListMySessions(seed.factory.for_tenant(seed.tenant.id), clock).execute(
        seed.doctor_actor
    )
    assert [s.id for s in sessions] == [live_sid]


def test_revoke_my_session_closes_a_remote_one():
    seed = seed_clinic()
    clock = FixedClock()
    sid = _login(seed, clock, seed.doctor.email)

    RevokeMySession(seed.factory.for_tenant(seed.tenant.id), clock).execute(
        seed.doctor_actor, sid
    )
    assert not seed.factory.store.sessions[sid.value].is_active(clock.now())


def test_cannot_revoke_someone_elses_session():
    seed = seed_clinic()
    clock = FixedClock()
    nurse_sid = _login(seed, clock, seed.nurse.email)

    with pytest.raises(EntityNotFound):
        RevokeMySession(seed.factory.for_tenant(seed.tenant.id), clock).execute(
            seed.doctor_actor, nurse_sid
        )
    assert seed.factory.store.sessions[nurse_sid.value].is_active(clock.now())


def test_admin_lists_user_sessions_with_name():
    seed = seed_clinic()
    clock = FixedClock()
    _login(seed, clock, seed.doctor.email)

    sessions = ListUserSessions(seed.factory.for_tenant(seed.tenant.id), clock).execute(
        seed.actor(seed.admin), seed.doctor.id
    )
    assert len(sessions) == 1
    assert sessions[0].user_name == seed.doctor.name
    assert sessions[0].role == "doctor"


def test_admin_revokes_one_user_session_and_audits():
    seed = seed_clinic()
    clock = FixedClock()
    sid = _login(seed, clock, seed.doctor.email)

    uow = seed.factory.for_tenant(seed.tenant.id)
    RevokeUserSession(uow, clock).execute(seed.actor(seed.admin), seed.doctor.id, sid)
    assert not seed.factory.store.sessions[sid.value].is_active(clock.now())
    assert uow.audit.query(action="session.revoked")


def test_admin_revokes_all_user_sessions():
    seed = seed_clinic()
    clock = FixedClock()
    sid1 = _login(seed, clock, seed.doctor.email)
    sid2 = _login(seed, clock, seed.doctor.email)

    uow = seed.factory.for_tenant(seed.tenant.id)
    RevokeAllUserSessions(uow, clock).execute(seed.actor(seed.admin), seed.doctor.id)
    assert not seed.factory.store.sessions[sid1.value].is_active(clock.now())
    assert not seed.factory.store.sessions[sid2.value].is_active(clock.now())
    assert uow.audit.query(action="session.revoked")


def test_non_admin_cannot_manage_other_sessions():
    seed = seed_clinic()
    clock = FixedClock()
    sid = _login(seed, clock, seed.doctor.email)
    uow = seed.factory.for_tenant(seed.tenant.id)

    with pytest.raises(PermissionDenied):
        ListUserSessions(uow, clock).execute(seed.receptionist_actor, seed.doctor.id)
    with pytest.raises(PermissionDenied):
        RevokeUserSession(uow, clock).execute(seed.receptionist_actor, seed.doctor.id, sid)


def test_platform_lists_tenant_sessions_with_names():
    seed = seed_clinic()
    clock = FixedClock()
    _login(seed, clock, seed.doctor.email)
    _login(seed, clock, seed.nurse.email)

    actor = PlatformActorContext(admin_id=seed.platform_admin.id)
    sessions = ListTenantSessions(seed.factory, clock).execute(actor, seed.tenant.id)
    assert {s.user_name for s in sessions} == {seed.doctor.name, seed.nurse.name}


def test_platform_revokes_tenant_session_and_audits():
    seed = seed_clinic()
    clock = FixedClock()
    sid = _login(seed, clock, seed.doctor.email)

    actor = PlatformActorContext(admin_id=seed.platform_admin.id)
    RevokeTenantSession(seed.factory, clock).execute(actor, seed.tenant.id, sid)
    assert not seed.factory.store.sessions[sid.value].is_active(clock.now())
    uow = seed.factory.platform_uow()
    assert any(e.action == "session.revoked" for e in uow.platform_audit.list())
