"""Access policy: who may hold a clinic session."""

from __future__ import annotations

import pytest

from medicore.domain.enums import Role, TenantStatus, UserStatus
from medicore.domain.services.access_policy import AccessRefused, ensure_may_access
from tests.support.builders import build_tenant, build_user


def _refusal(tenant, user, **kwargs) -> str:
    with pytest.raises(AccessRefused) as exc:
        ensure_may_access(tenant, user, **kwargs)
    return exc.value.code


@pytest.fixture
def tenant():
    return build_tenant()


@pytest.fixture
def user(tenant):
    return build_user(tenant.id, Role.DOCTOR)


def test_active_user_in_active_clinic_may_access(tenant, user):
    ensure_may_access(tenant, user)


@pytest.mark.parametrize("status", [TenantStatus.SUSPENDED, TenantStatus.ARCHIVED])
def test_inactive_clinic_is_refused(tenant, user, status):
    tenant.status = status
    assert _refusal(tenant, user) == "auth.organization_inactive"


@pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.PENDING])
def test_inactive_account_is_refused(tenant, user, status):
    user.status = status
    assert _refusal(tenant, user) == "auth.account_inactive"


def test_clinic_is_checked_before_account(tenant, user):
    tenant.status = TenantStatus.SUSPENDED
    user.status = UserStatus.SUSPENDED
    assert _refusal(tenant, user) == "auth.organization_inactive"


def test_support_reaches_a_suspended_clinic(tenant, user):
    tenant.status = TenantStatus.SUSPENDED
    ensure_may_access(tenant, user, support=True)


def test_support_never_reaches_an_archived_clinic(tenant, user):
    tenant.status = TenantStatus.ARCHIVED
    assert _refusal(tenant, user, support=True) == "auth.organization_inactive"


def test_support_still_needs_an_active_account(tenant, user):
    tenant.status = TenantStatus.SUSPENDED
    user.status = UserStatus.SUSPENDED
    assert _refusal(tenant, user, support=True) == "auth.account_inactive"
