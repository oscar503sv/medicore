"""Platform-support actions on a clinic's accounts leave a trail the clinic can see."""

from __future__ import annotations

import pytest

from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.errors import TooManyLoginAttempts, ValidationError
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.platform import (
    EndImpersonation,
    ImpersonateTenant,
    ListGlobalAudit,
    ReactivateTenantUser,
    ResetUserPassword,
    SuspendTenantUser,
    UpdateTenantUser,
)
from medicore.domain.enums import Role, UserStatus
from tests.support.builders import PASSWORD, build_user, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher

REASON = "Customer asked for help"
SUPPORT_IP = "203.0.113.9"


def _actor(seed) -> PlatformActorContext:
    return PlatformActorContext(
        admin_id=seed.platform_admin.id, ip_address="198.51.100.7", user_agent="console"
    )


def _clinic_audit(seed, action: str):
    return [e for e in seed.factory.for_tenant(seed.tenant.id).audit.query() if e.action == action]


def _platform_audit(seed, action: str):
    return [e for e in seed.factory.store.platform_audit.values() if e.action == action]


def _inbox(seed, user):
    return seed.factory.for_tenant(seed.tenant.id).notifications.list_by_user(user.id)


def _reset(seed, user=None, password="Volcan-Izalco-77", reason=REASON):
    return ResetUserPassword(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
        _actor(seed), seed.tenant.id, (user or seed.doctor).id, password, reason
    )


def _suspend(seed):
    return SuspendTenantUser(seed.factory, FixedClock()).execute(
        _actor(seed), seed.tenant.id, seed.doctor.id
    )


def _reactivate(seed):
    seed.doctor.status = UserStatus.SUSPENDED
    return ReactivateTenantUser(seed.factory, FixedClock()).execute(
        _actor(seed), seed.tenant.id, seed.doctor.id
    )


def _promote(seed):
    return UpdateTenantUser(seed.factory, FixedClock()).execute(
        _actor(seed), seed.tenant.id, seed.doctor.id, role=Role.ADMIN
    )


def _login(seed, email, password, ip=SUPPORT_IP):
    return AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock()
    ).execute(
        AuthenticateUserCommand(
            slug=str(seed.tenant.slug), email=email, password=password, ip_address=ip
        )
    )


def test_reset_is_visible_in_the_clinic_audit_and_keeps_the_reason_on_the_platform():
    seed = seed_clinic()
    _reset(seed)

    [entry] = _clinic_audit(seed, "user.password_reset")
    assert entry.entity_id == str(seed.doctor.id)
    assert entry.actor_id.value == seed.platform_admin.id.value
    assert entry.ip_address == "198.51.100.7"
    assert entry.metadata == {
        "via": "platform_support",
        "reason": REASON,
        "subject": seed.doctor.name,
    }
    [console] = _platform_audit(seed, "user.password_reset")
    assert console.metadata["reason"] == REASON


@pytest.mark.parametrize(
    ("action", "act", "notification"),
    [
        ("user.password_reset", _reset, "support.password_reset"),
        ("user.updated", _promote, "support.user_updated"),
        ("user.suspended", _suspend, "support.user_suspended"),
        ("user.reactivated", _reactivate, "support.user_reactivated"),
    ],
)
def test_each_account_action_audits_and_notifies_the_admins_and_the_person(
    action, act, notification
):
    seed = seed_clinic()
    act(seed)

    [entry] = _clinic_audit(seed, action)
    assert entry.metadata["via"] == "platform_support"
    admin_copies = _inbox(seed, seed.admin)
    doctor_copies = _inbox(seed, seed.doctor)
    assert [n.type for n in admin_copies] == [notification]
    assert [n.type for n in doctor_copies] == [notification]
    assert doctor_copies[0].data["about_you"] == "true"
    assert doctor_copies[0].data["user_name"] == seed.doctor.name
    assert "about_you" not in admin_copies[0].data
    assert _inbox(seed, seed.nurse) == []


def test_an_admin_concerned_gets_a_single_second_person_copy():
    seed = seed_clinic()
    second = build_user(seed.tenant.id, Role.ADMIN, name="Second Admin", email="a2@clinica.test")
    seed.factory.store.users[second.id.value] = second
    _reset(seed, second)

    [own] = _inbox(seed, second)
    assert own.data["about_you"] == "true"
    [other] = _inbox(seed, seed.admin)
    assert "about_you" not in other.data


def test_an_update_that_changes_nothing_stays_off_the_clinic_trail():
    seed = seed_clinic()
    UpdateTenantUser(seed.factory, FixedClock()).execute(
        _actor(seed), seed.tenant.id, seed.doctor.id, name=seed.doctor.name
    )

    assert _clinic_audit(seed, "user.updated") == []
    assert seed.factory.store.notifications == {}
    assert len(_platform_audit(seed, "user.updated")) == 1


def test_a_role_change_records_the_fields_and_both_roles():
    seed = seed_clinic()
    _promote(seed)

    [entry] = _clinic_audit(seed, "user.updated")
    assert entry.metadata["fields"] == "role"
    assert entry.metadata["role"] == "admin"
    assert entry.metadata["previous_role"] == "doctor"


def test_a_reset_refused_by_the_password_policy_leaves_no_trace():
    seed = seed_clinic()
    with pytest.raises(ValidationError):
        _reset(seed, password="aaaaaaaaaa")

    assert _clinic_audit(seed, "user.password_reset") == []
    assert _platform_audit(seed, "user.password_reset") == []
    assert seed.factory.store.notifications == {}


@pytest.mark.parametrize("reason", ["", "  ", None])
def test_a_reset_without_reason_is_refused_and_keeps_the_hash(reason):
    seed = seed_clinic()
    before = seed.doctor.password_hash
    with pytest.raises(ValidationError) as caught:
        _reset(seed, reason=reason)

    assert caught.value.code == "support.reason_required"
    assert seed.factory.store.users[seed.doctor.id.value].password_hash == before


def _impersonate(seed, reason=REASON):
    return ImpersonateTenant(seed.factory, FakeTokenIssuer(), FixedClock()).execute(
        _actor(seed), seed.tenant.id, reason
    )


def test_impersonation_is_audited_in_the_clinic_and_notifies_only_admins():
    seed = seed_clinic()
    _impersonate(seed)

    [entry] = _clinic_audit(seed, "support.access.started")
    assert entry.entity_type == "Tenant"
    assert entry.metadata["via"] == "platform_support"
    assert entry.metadata["reason"] == REASON
    assert entry.metadata["as_user"] == str(seed.admin.id)
    assert entry.metadata["subject"] == seed.admin.name
    assert [n.type for n in _inbox(seed, seed.admin)] == ["support.access_started"]
    assert _inbox(seed, seed.doctor) == []
    assert "reason" not in _inbox(seed, seed.admin)[0].data


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("", "support.reason_required"),
        ("    ", "support.reason_required"),
        ("abc", "support.reason_required"),
        ("x" * 501, "support.reason_too_long"),
    ],
)
def test_an_invalid_impersonation_reason_opens_nothing(reason, code):
    seed = seed_clinic()
    with pytest.raises(ValidationError) as caught:
        _impersonate(seed, reason)

    assert caught.value.code == code
    assert seed.factory.store.sessions == {}
    assert _clinic_audit(seed, "support.access.started") == []
    assert _platform_audit(seed, "support.access.started") == []


def test_ending_a_support_session_is_audited_in_the_clinic():
    seed = seed_clinic()
    _impersonate(seed)
    actor = ActorContext(
        user_id=seed.admin.id,
        tenant_id=seed.tenant.id,
        role=Role.ADMIN,
        impersonated_by=seed.platform_admin.id.value,
    )
    EndImpersonation(seed.factory, FixedClock()).execute(actor)

    [entry] = _clinic_audit(seed, "support.access.ended")
    assert entry.metadata["impersonated_by"] == str(seed.platform_admin.id.value)


def _lock_out(seed):
    for _ in range(5):
        with pytest.raises(Exception):  # noqa: B017  (any failed sign-in)
            _login(seed, seed.doctor.email, "wrong-password")
    with pytest.raises(TooManyLoginAttempts):
        _login(seed, seed.doctor.email, "wrong-password")


def test_a_support_reset_lifts_the_login_lockout():
    seed = seed_clinic()
    _lock_out(seed)
    _reset(seed)

    assert _login(seed, seed.doctor.email, "Volcan-Izalco-77").must_change_password
    assert seed.factory.store.login_attempts[f"ip:{SUPPORT_IP}"][0] > 0


def test_a_reactivation_lifts_the_login_lockout():
    seed = seed_clinic()
    _lock_out(seed)
    seed.doctor.status = UserStatus.SUSPENDED
    ReactivateTenantUser(seed.factory, FixedClock()).execute(
        _actor(seed), seed.tenant.id, seed.doctor.id
    )

    assert _login(seed, seed.doctor.email, PASSWORD).token
    assert seed.factory.store.login_attempts[f"ip:{SUPPORT_IP}"][0] > 0


def test_clearing_an_account_touches_only_its_own_counters():
    seed = seed_clinic()
    now = FixedClock().now()
    attempts = seed.factory.store.login_attempts
    for key in ("tenant:t:a@x.test", "tenant:t:a@x.test|1.1.1.1", "tenant:t:a@x.test.mx|1.1.1.1",
                "ip:1.1.1.1"):
        attempts[key] = (5, now, now)

    with seed.factory.login_throttle() as throttle:
        throttle.clear_account("tenant:t:a@x.test")

    assert attempts["tenant:t:a@x.test"] == (0, now, None)
    assert attempts["tenant:t:a@x.test|1.1.1.1"] == (0, now, None)
    assert attempts["tenant:t:a@x.test.mx|1.1.1.1"] == (5, now, now)
    assert attempts["ip:1.1.1.1"] == (5, now, now)


def test_the_global_audit_shows_a_support_action_once():
    seed = seed_clinic()
    _reset(seed)

    page = ListGlobalAudit(seed.factory).execute(_actor(seed))
    rows = [r for r in page.items if r.action == "user.password_reset"]
    assert [r.source_kind for r in rows] == ["platform"]
