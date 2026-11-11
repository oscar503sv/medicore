"""Subscriptions: the editable plan catalog and each clinic's plan, modules and period.

Activation and renewal are manual (bank transfer): the platform console sets them. A clinic
can only read its own subscription. Enforcement (quotas, modules, read-only) lives in the
places that create users/sites and resolve permissions, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from medicore.application.common.audit import platform_audit_entry
from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.quotas import active_by_role
from medicore.application.common.timezone import tenant_today
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import (
    PlatformUnitOfWork,
    UnitOfWork,
    UnitOfWorkFactory,
)
from medicore.domain.entities.plan import CURRENCY, AddonPricing, Plan
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import AddonModule, PlanFeature, SubscriptionStatus
from medicore.domain.services.seat_usage import SeatUsage, seat_usage
from medicore.domain.services.subscription_pricing import monthly_quote
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.domain.value_objects.subscription import DEFAULT_TRIAL_DAYS, Subscription


def _usd(amount: Decimal | None) -> Money | None:
    return None if amount is None else Money(amount, CURRENCY)


# ── Read model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    """A clinic's subscription resolved against the catalog, with current usage."""

    subscription: Subscription
    plan: Plan
    status: SubscriptionStatus
    today: date
    days_left: int | None
    limits: PlanLimits  # plan quotas with the clinic's overrides applied
    usage: SeatUsage
    locations_used: int
    monthly_price: Money | None
    addon_prices: AddonPricing


def build_view(uow: UnitOfWork, tenant: Tenant, clock: Clock) -> SubscriptionView:
    """Must run inside ``uow`` (tenant-scoped, for the user counts)."""
    sub = tenant.subscription
    plan = uow.plans.get(sub.plan_code)
    if plan is None:  # guarded by a foreign key; only a broken database gets here
        raise EntityNotFound("Plan", sub.plan_code)
    addons = uow.addon_pricing.get()
    today = tenant_today(tenant, clock)
    return SubscriptionView(
        subscription=sub,
        plan=plan,
        status=sub.status(today),
        today=today,
        days_left=sub.days_left(today),
        limits=plan.limits.overridden_by(sub.limit_overrides),
        usage=seat_usage(active_by_role(uow)),
        locations_used=len(tenant.locations),
        monthly_price=monthly_quote(sub, plan, addons),
        addon_prices=addons,
    )


def _subscription_summary(sub: Subscription) -> dict[str, object]:
    """Audit metadata: what the subscription looked like, JSON-friendly."""
    overrides = sub.limit_overrides
    return {
        "plan": sub.plan_code,
        "modules": sorted(str(m) for m in sub.modules),
        "period_end": sub.period_end.isoformat() if sub.period_end else None,
        "is_trial": sub.is_trial,
        "grace_days": sub.grace_days,
        "limits": None if overrides is None else {
            "doctors": overrides.doctors,
            "support_users": overrides.support_users,
            "locations": overrides.locations,
            "storage_gb": overrides.storage_gb,
        },
        "price": str(sub.price_override.amount) if sub.price_override else None,
    }


# ── Catalog (platform) ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Catalog:
    plans: list[Plan]
    addons: AddonPricing


class GetCatalog:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext) -> Catalog:
        with self._factory.platform_uow() as uow:
            return Catalog(plans=uow.plans.list(), addons=uow.addon_pricing.get())


@dataclass(frozen=True, slots=True)
class UpdatePlanCommand:
    name: str
    monthly_price: Decimal | None  # None: custom quote per clinic
    limits: PlanLimits
    features: frozenset[PlanFeature]
    active: bool


class UpdatePlan:
    """Change a plan's name, price, quotas or features. Applies to every clinic on it from
    now on; payments already recorded keep the price they were made at."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, actor: PlatformActorContext, code: str, cmd: UpdatePlanCommand) -> Plan:
        with self._factory.platform_uow() as uow:
            plan = uow.plans.get(code)
            if plan is None:
                raise EntityNotFound("Plan", code)
            before = _plan_summary(plan)
            plan.update(
                name=cmd.name,
                monthly_price=_usd(cmd.monthly_price),
                limits=cmd.limits,
                features=cmd.features,
                active=cmd.active,
            )
            uow.plans.save(plan)
            uow.platform_audit.append(
                platform_audit_entry(
                    actor, self._clock.now(), "plan.updated", "Plan", code,
                    subject=plan.name, before=before, after=_plan_summary(plan),
                )
            )
            uow.commit()
        return plan


def _plan_summary(plan: Plan) -> dict[str, object]:
    return {
        "name": plan.name,
        "price": str(plan.monthly_price.amount) if plan.monthly_price else None,
        "doctors": plan.limits.doctors,
        "support_users": plan.limits.support_users,
        "locations": plan.limits.locations,
        "storage_gb": plan.limits.storage_gb,
        "features": sorted(str(f) for f in plan.features),
        "active": plan.active,
    }


class UpdateAddonPricing:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self,
        actor: PlatformActorContext,
        prices: dict[AddonModule, Decimal],
        bundle_price: Decimal,
    ) -> AddonPricing:
        with self._factory.platform_uow() as uow:
            pricing = uow.addon_pricing.get()
            before = _pricing_summary(pricing)
            pricing.update(
                {m: Money(p, CURRENCY) for m, p in prices.items()}, Money(bundle_price, CURRENCY)
            )
            uow.addon_pricing.save(pricing)
            uow.platform_audit.append(
                platform_audit_entry(
                    actor, self._clock.now(), "addon_pricing.updated", "AddonPricing", "current",
                    before=before, after=_pricing_summary(pricing),
                )
            )
            uow.commit()
        return pricing


def _pricing_summary(pricing: AddonPricing) -> dict[str, str]:
    summary = {str(m): str(p.amount) for m, p in pricing.prices.items()}
    summary["bundle"] = str(pricing.bundle_price.amount)
    return summary


# ── A clinic's subscription (platform) ────────────────────────────────────────


class GetTenantSubscription:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, actor: PlatformActorContext, tenant_id: TenantId) -> SubscriptionView:
        with self._factory.for_tenant(tenant_id) as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", tenant_id)
            return build_view(uow, tenant, self._clock)


@dataclass(frozen=True, slots=True)
class SubscriptionCommand:
    plan_code: str
    modules: frozenset[AddonModule]
    period_end: date | None
    is_trial: bool
    grace_days: int
    limit_overrides: LimitOverrides | None = None
    price_override: Decimal | None = None


def resolve_subscription(
    uow: UnitOfWork | PlatformUnitOfWork, cmd: SubscriptionCommand, current: str | None = None
) -> Subscription:
    """Validate a requested subscription against the catalog. An inactive plan can't be
    chosen, except by the clinic already on it (editing its modules or dates)."""
    plan = uow.plans.get(cmd.plan_code)
    if plan is None or (not plan.active and plan.code != current):
        raise ValidationError(
            f"unknown or inactive plan: {cmd.plan_code}", code="plan.unavailable",
            plan=cmd.plan_code,
        )
    return Subscription(
        plan_code=plan.code,
        modules=cmd.modules,
        period_end=cmd.period_end,
        is_trial=cmd.is_trial,
        grace_days=cmd.grace_days,
        limit_overrides=cmd.limit_overrides,
        price_override=_usd(cmd.price_override),
    )


class UpdateTenantSubscription:
    """Set a clinic's plan, modules, period and custom terms. Changing plan never deletes
    or locks data; quotas only stop new activations above them."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, cmd: SubscriptionCommand
    ) -> SubscriptionView:
        with self._factory.for_tenant(tenant_id) as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", tenant_id)
            before = tenant.subscription
            tenant.subscription = resolve_subscription(uow, cmd, current=before.plan_code)
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                platform_audit_entry(
                    actor, self._clock.now(), "tenant.subscription_updated", "Tenant",
                    str(tenant_id), tenant_id=tenant_id, subject=tenant.legal_name,
                    before=_subscription_summary(before),
                    after=_subscription_summary(tenant.subscription),
                )
            )
            uow.commit()
            return build_view(uow, tenant, self._clock)


class StartTrial:
    """Put a clinic on a free trial of ``days`` days starting today (7 by default)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, days: int = DEFAULT_TRIAL_DAYS
    ) -> SubscriptionView:
        with self._factory.for_tenant(tenant_id) as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", tenant_id)
            tenant.subscription = tenant.subscription.start_trial(
                tenant_today(tenant, self._clock), days
            )
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                platform_audit_entry(
                    actor, self._clock.now(), "tenant.trial_started", "Tenant", str(tenant_id),
                    tenant_id=tenant_id, subject=tenant.legal_name, days=days,
                    period_end=tenant.subscription.period_end.isoformat(),
                )
            )
            uow.commit()
            return build_view(uow, tenant, self._clock)


# ── The clinic's own view ─────────────────────────────────────────────────────


class GetMySubscription:
    """The clinic admin's read-only view of its plan (Settings → Organization)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> SubscriptionView:
        ensure_permission(actor, Permission.ORGANIZATION_VIEW)
        with self._uow:
            tenant = self._uow.tenants.get_by_id(actor.tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", actor.tenant_id)
            return build_view(self._uow, tenant, self._clock)
