"""Subscription quotas, checked wherever a seat or a site is taken: inviting, reactivating
or re-roling a user, and adding a location. The rule itself is in the domain
(``seat_usage.check_quota``); this resolves the clinic's limits and current usage."""

from __future__ import annotations

from medicore.application.common.errors import EntityNotFound
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import Role, UserStatus
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.services.seat_usage import (
    QUOTA_LOCATIONS,
    check_quota,
    ensure_seats,
    seat_usage,
)
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.plan_limits import PlanLimits


def active_by_role(uow: UnitOfWork) -> dict[Role, int]:
    """Active users per role in the unit of work's clinic."""
    active = str(UserStatus.ACTIVE)
    return {
        role: uow.users.list(UserFilter(role=str(role), status=active), Paging(limit=1)).total
        for role in Role
    }


def effective_limits(uow: UnitOfWork, tenant: Tenant) -> PlanLimits:
    """The plan's quotas with the clinic's own overrides applied."""
    sub = tenant.subscription
    plan = uow.plans.get(sub.plan_code)
    if plan is None:  # guarded by a foreign key; only a broken database gets here
        raise EntityNotFound("Plan", sub.plan_code)
    return plan.limits.overridden_by(sub.limit_overrides)


def _tenant(uow: UnitOfWork, tenant_id: TenantId) -> Tenant:
    tenant = uow.tenants.get_by_id(tenant_id)
    if tenant is None:
        raise EntityNotFound("Tenant", tenant_id)
    return tenant


def ensure_seat_for(
    uow: UnitOfWork,
    tenant_id: TenantId,
    *,
    taking: Role | None = None,
    releasing: Role | None = None,
) -> None:
    """Check that an active user taking the ``taking`` role's seat (and, on a role change,
    freeing the ``releasing`` one) fits the subscription. Raises ``QuotaExceeded``."""
    if taking is None or taking == releasing:
        return
    counts = active_by_role(uow)
    after = dict(counts)
    after[taking] = after.get(taking, 0) + 1
    if releasing is not None:
        after[releasing] = max(after.get(releasing, 0) - 1, 0)
    limits = effective_limits(uow, _tenant(uow, tenant_id))
    ensure_seats(limits, seat_usage(counts), seat_usage(after))


def ensure_location_for(uow: UnitOfWork, tenant: Tenant) -> None:
    """Check there is room for one more site. Raises ``QuotaExceeded``."""
    used = len(tenant.locations)
    check_quota(QUOTA_LOCATIONS, effective_limits(uow, tenant).locations, used, used + 1)
