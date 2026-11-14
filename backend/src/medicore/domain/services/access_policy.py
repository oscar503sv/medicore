"""Who may hold a clinic session: the single rule behind login, every authenticated
request and support access."""

from __future__ import annotations

from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import TenantStatus
from medicore.domain.shared.errors import DomainError


class AccessRefused(DomainError):
    """The clinic or the account may not hold a session right now."""


def admits(tenant: Tenant, *, support: bool = False) -> bool:
    """Whether the clinic accepts sessions: only while active, except support access,
    which still reaches a suspended clinic (helping it is often why it's suspended) but
    never an archived one."""
    if support:
        return tenant.status != TenantStatus.ARCHIVED
    return tenant.is_active


def ensure_may_access(tenant: Tenant, user: User, *, support: bool = False) -> None:
    if not admits(tenant, support=support):
        raise AccessRefused("this organization is not active", code="auth.organization_inactive")
    if not user.is_active:
        raise AccessRefused("account is not active", code="auth.account_inactive")
