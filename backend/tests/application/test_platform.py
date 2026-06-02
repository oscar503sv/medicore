"""Tests for platform (superadmin) use cases."""

from __future__ import annotations

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import AuthenticationFailed, ValidationError
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.platform import (
    AuthenticatePlatformAdmin,
    CreateTenantCommand,
    CreateTenantWithAdmin,
    ListTenants,
    SetTenantStatus,
    UpdateTenant,
)
from medicore.domain.enums import IcdVersion, TenantStatus, UserStatus
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
