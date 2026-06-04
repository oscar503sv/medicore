"""Tests for platform (superadmin) use cases."""

from __future__ import annotations

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import (
    AuthenticationFailed,
    EntityNotFound,
    ValidationError,
)
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.platform import (
    AuthenticatePlatformAdmin,
    CreateTenantCommand,
    CreateTenantWithAdmin,
    GetGlobalStats,
    GetTenantStats,
    ImpersonateTenant,
    ListGlobalAudit,
    ListTenants,
    ResetUserPassword,
    SetTenantStatus,
    SuspendTenantUser,
    UnlockUser,
    UpdateTenant,
    UpdateTenantUser,
)
from medicore.domain.enums import IcdVersion, Role, TenantStatus, UserStatus
from medicore.domain.shared.identifiers import UserId
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher


def make_platform_auth(seed):
    return AuthenticatePlatformAdmin(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock()
    )


def actor_for(seed) -> PlatformActorContext:
    return PlatformActorContext(admin_id=seed.platform_admin.id)


def test_platform_login_success():
    seed = seed_clinic()
    session = make_platform_auth(seed).execute(seed.platform_admin.email, PASSWORD)
    assert session.admin_id == seed.platform_admin.id
    claims = FakeTokenIssuer().decode(session.token)
    assert claims.scope == "platform"
    assert claims.tenant_id is None


def test_platform_login_wrong_password():
    seed = seed_clinic()
    with pytest.raises(AuthenticationFailed):
        make_platform_auth(seed).execute(seed.platform_admin.email, "nope")


def test_create_tenant_with_admin():
    seed = seed_clinic()
    cmd = CreateTenantCommand(
        legal_name="Clínica Sur SL",
        tax_id="B99",
        slug="clinica-sur",
        timezone="Europe/Madrid",
        location_name="Sevilla",
        admin_name="Admin Sur",
        admin_email="admin@sur.test",
        admin_password="temp-pass-123",
    )
    result = CreateTenantWithAdmin(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
        actor_for(seed), cmd
    )
    assert result.tenant.icd_version == IcdVersion.CIE11  # default
    assert result.admin.must_change_password is True
    # the new admin can authenticate against the new clinic
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock())
    session = auth.execute(
        AuthenticateUserCommand(
            slug="clinica-sur", email="admin@sur.test", password="temp-pass-123"
        )
    )
    assert session.must_change_password is True
    # platform audit recorded
    assert seed.factory.platform_uow().platform_audit.list()


def test_create_tenant_duplicate_slug_rejected():
    seed = seed_clinic()
    cmd = CreateTenantCommand(
        legal_name="Dup", tax_id="B1", slug="clinica-norte", timezone="Europe/Madrid",
        location_name="X", admin_name="A", admin_email="a@x.test", admin_password="temp-pass-123",
    )
    with pytest.raises(ValidationError):
        CreateTenantWithAdmin(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
            actor_for(seed), cmd
        )


def test_suspended_tenant_blocks_login():
    seed = seed_clinic()
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.SUSPENDED
    )
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock())
    with pytest.raises(AuthenticationFailed):
        auth.execute(
            AuthenticateUserCommand(
                slug="clinica-norte", email=seed.doctor.email, password=PASSWORD
            )
        )


def test_reactivated_tenant_allows_login():
    seed = seed_clinic()
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.SUSPENDED
    )
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.ACTIVE
    )
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock())
    session = auth.execute(
        AuthenticateUserCommand(slug="clinica-norte", email=seed.doctor.email, password=PASSWORD)
    )
    assert session.role.value == "doctor"


def test_update_tenant_changes_icd_version():
    seed = seed_clinic()
    tenant = UpdateTenant(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, icd_version="cie10", plan="enterprise"
    )
    assert tenant.icd_version == IcdVersion.CIE10
    assert tenant.plan == "enterprise"


def test_list_tenants_filters_by_status():
    seed = seed_clinic()
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.ARCHIVED
    )
    page = ListTenants(seed.factory).execute(actor_for(seed))
    assert page.total == 1
    assert page.items[0].status == TenantStatus.ARCHIVED
    assert seed.platform_admin.status == UserStatus.ACTIVE


def test_global_stats_counts():
    seed = seed_clinic()
    stats = GetGlobalStats(seed.factory).execute(actor_for(seed))
    assert stats.total_clinics == 1
    assert stats.total_users == 4  # admin, doctor, nurse, receptionist
    assert stats.total_patients == 1
    assert stats.by_clinic[0].tenant_id == str(seed.tenant.id)


def test_tenant_stats_counts():
    seed = seed_clinic()
    stats = GetTenantStats(seed.factory).execute(actor_for(seed), seed.tenant.id)
    assert stats.users == 4
    assert stats.patients == 1


def test_reset_user_password_sets_temporary():
    seed = seed_clinic()
    user = ResetUserPassword(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
        actor_for(seed), seed.tenant.id, seed.doctor.id, "brand-new-pass"
    )
    assert user.must_change_password is True
    assert seed.factory.platform_uow().platform_audit.list()


def test_unlock_user_reactivates():
    seed = seed_clinic()
    seed.doctor.status = UserStatus.SUSPENDED
    seed.factory.store.users[seed.doctor.id.value] = seed.doctor
    user = UnlockUser(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, seed.doctor.id
    )
    assert user.status == UserStatus.ACTIVE


def test_update_tenant_user_edits_profile_and_audits():
    seed = seed_clinic()
    user = UpdateTenantUser(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, seed.doctor.id,
        name="Dra. Nueva", role=Role.ADMIN, specialty="Cardiología",
    )
    assert user.name == "Dra. Nueva"
    assert user.role == Role.ADMIN
    assert user.specialty == "Cardiología"
    audit = seed.factory.platform_uow().platform_audit.list()
    assert any(e.action == "user.updated" for e in audit)


def test_update_tenant_user_rejects_cross_tenant_user():
    seed = seed_clinic()
    with pytest.raises(EntityNotFound):
        UpdateTenantUser(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id, UserId.new(), name="Ghost"
        )


def test_suspend_tenant_user_deactivates_and_audits():
    seed = seed_clinic()
    user = SuspendTenantUser(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, seed.doctor.id
    )
    assert user.status == UserStatus.SUSPENDED
    audit = seed.factory.platform_uow().platform_audit.list()
    assert any(e.action == "user.suspended" for e in audit)


def test_platform_audit_records_affected_tenant_id():
    seed = seed_clinic()
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.SUSPENDED
    )
    entry = next(
        e
        for e in seed.factory.platform_uow().platform_audit.list()
        if e.action == "tenant.suspended"
    )
    assert entry.tenant_id == seed.tenant.id


def test_global_audit_reads_tenant_trail():
    seed = seed_clinic()
    auth = AuthenticateUser(seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock())
    auth.execute(
        AuthenticateUserCommand(slug="clinica-norte", email=seed.doctor.email, password=PASSWORD)
    )
    entries = ListGlobalAudit(seed.factory).execute(actor_for(seed))
    assert any(e.action == "auth.login" for e in entries)


def test_impersonation_token_carries_impersonator():
    seed = seed_clinic()
    session = ImpersonateTenant(seed.factory, FakeTokenIssuer(), FixedClock()).execute(
        actor_for(seed), seed.tenant.id
    )
    claims = FakeTokenIssuer().decode(session.token)
    assert claims.scope == "tenant"
    assert claims.impersonator == str(seed.platform_admin.id)
    assert claims.user_id == str(seed.admin.id)  # impersonates the clinic's admin
    assert seed.factory.platform_uow().platform_audit.list()


def test_impersonation_rejected_for_archived_clinic():
    seed = seed_clinic()
    SetTenantStatus(seed.factory, FixedClock()).execute(
        actor_for(seed), seed.tenant.id, TenantStatus.ARCHIVED
    )
    with pytest.raises(ValidationError):
        ImpersonateTenant(seed.factory, FakeTokenIssuer(), FixedClock()).execute(
            actor_for(seed), seed.tenant.id
        )


def test_audit_entry_marks_impersonation():
    from medicore.application.common.audit import audit_entry
    from medicore.application.common.context import ActorContext

    seed = seed_clinic()
    actor = ActorContext(
        user_id=seed.admin.id,
        tenant_id=seed.tenant.id,
        role=seed.admin.role,
        impersonated_by=seed.platform_admin.id,
    )
    entry = audit_entry(actor, FixedClock().now(), "patient.created", "Patient", "x")
    assert entry.metadata["impersonated_by"] == str(seed.platform_admin.id)
