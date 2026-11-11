"""Row ↔ domain mapping for the subscription catalog and a tenant's subscription."""

from __future__ import annotations

from decimal import Decimal

from medicore.domain.entities.plan import CURRENCY, AddonPricing, Plan
from medicore.domain.enums import AddonModule, PlanFeature
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.domain.value_objects.subscription import Subscription
from medicore.infrastructure.persistence.models.subscription import AddonPricingModel, PlanModel
from medicore.infrastructure.persistence.models.tenant import TenantModel


def _usd(amount: Decimal | str | None) -> Money | None:
    return None if amount is None else Money(Decimal(amount), CURRENCY)


def to_plan(row: PlanModel) -> Plan:
    return Plan(
        code=row.code,
        name=row.name,
        monthly_price=_usd(row.monthly_price),
        limits=PlanLimits(
            doctors=row.limit_doctors,
            support_users=row.limit_support_users,
            locations=row.limit_locations,
            storage_gb=row.limit_storage_gb,
        ),
        # Unknown strings (a feature removed from the code) are dropped, never fatal.
        features=frozenset(PlanFeature(f) for f in row.features if f in PlanFeature),
        active=row.active,
        sort_order=row.sort_order,
    )


def plan_to_row(plan: Plan, row: PlanModel) -> None:
    row.name = plan.name
    row.monthly_price = plan.monthly_price.amount if plan.monthly_price else None
    row.limit_doctors = plan.limits.doctors
    row.limit_support_users = plan.limits.support_users
    row.limit_locations = plan.limits.locations
    row.limit_storage_gb = plan.limits.storage_gb
    row.features = sorted(str(f) for f in plan.features)
    row.active = plan.active
    row.sort_order = plan.sort_order


def to_addon_pricing(row: AddonPricingModel) -> AddonPricing:
    return AddonPricing(
        prices={AddonModule(k): _usd(v) for k, v in row.prices.items() if k in AddonModule},
        bundle_price=_usd(row.bundle_price),
    )


def addon_pricing_to_row(pricing: AddonPricing, row: AddonPricingModel) -> None:
    row.prices = {str(m): str(p.amount) for m, p in pricing.prices.items()}
    row.bundle_price = pricing.bundle_price.amount


def subscription_from_row(row: TenantModel) -> Subscription:
    return Subscription(
        plan_code=row.plan_code,
        modules=frozenset(AddonModule(m) for m in row.modules if m in AddonModule),
        period_end=row.period_end,
        is_trial=row.is_trial,
        grace_days=row.grace_days,
        limit_overrides=LimitOverrides(
            doctors=row.limit_doctors,
            support_users=row.limit_support_users,
            locations=row.limit_locations,
            storage_gb=row.limit_storage_gb,
        ),
        price_override=_usd(row.price_override),
    )


def subscription_to_row(sub: Subscription, row: TenantModel) -> None:
    overrides = sub.limit_overrides or LimitOverrides()
    row.plan_code = sub.plan_code
    row.modules = sorted(str(m) for m in sub.modules)
    row.period_end = sub.period_end
    row.is_trial = sub.is_trial
    row.grace_days = sub.grace_days
    row.limit_doctors = overrides.doctors
    row.limit_support_users = overrides.support_users
    row.limit_locations = overrides.locations
    row.limit_storage_gb = overrides.storage_gb
    row.price_override = sub.price_override.amount if sub.price_override else None
