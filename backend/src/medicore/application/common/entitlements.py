"""What a user may do in their clinic: the role's permissions (with the clinic's
customization) limited by the subscription's contracted modules, and whether the clinic
may write at all. Every place that hands out a permission set (request actor, login,
profile, support sessions) goes through here."""

from __future__ import annotations

from datetime import date

from medicore.application.common.permissions import Permission, granted
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import Role, SubscriptionStatus
from medicore.domain.shared.errors import SubscriptionReadOnly


def granted_permissions(uow: UnitOfWork, tenant: Tenant, role: Role) -> frozenset[Permission]:
    override = uow.role_permissions.get_by_role(role)
    return granted(
        role, override.permissions if override else None, tenant.subscription.modules
    )


def ensure_writable(tenant: Tenant, today: date) -> None:
    """A clinic whose subscription lapsed past its grace days keeps reading its data but
    can't change anything until it renews. Raises ``SubscriptionReadOnly``."""
    sub = tenant.subscription
    if sub.status(today) == SubscriptionStatus.READ_ONLY:
        raise SubscriptionReadOnly(
            "the subscription expired: the clinic is read-only until it renews",
            period_end=sub.period_end.isoformat() if sub.period_end else None,
        )
