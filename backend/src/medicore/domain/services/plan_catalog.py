"""The subscription catalog the platform starts with (the published price list). After
that it is data: prices and quotas are edited from the platform console."""

from __future__ import annotations

from decimal import Decimal

from medicore.domain.entities.plan import CURRENCY, AddonPricing, Plan
from medicore.domain.enums import AddonModule, AnalyticsTier, PlanFeature
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import PlanLimits


def _usd(amount: str) -> Money:
    return Money(Decimal(amount), CURRENCY)


INDEPENDIENTE = "independiente"
CLINICA = "clinica"
CLINICA_PLUS = "clinica_plus"
EMPRESARIAL = "empresarial"


def default_plans() -> list[Plan]:
    per_user = frozenset({PlanFeature.USER_PERMISSIONS})
    return [
        Plan(INDEPENDIENTE, "Profesional independiente", _usd("39"),
             PlanLimits(doctors=1, support_users=1, locations=1, storage_gb=2), sort_order=1,
             analytics_tier=AnalyticsTier.BASIC),
        Plan(CLINICA, "Clínica", _usd("79"),
             PlanLimits(doctors=3, support_users=3, locations=1, storage_gb=3), per_user,
             sort_order=2, analytics_tier=AnalyticsTier.CLINIC),
        Plan(CLINICA_PLUS, "Clínica Plus", _usd("119"),
             PlanLimits(doctors=5, support_users=6, locations=1, storage_gb=5), per_user,
             sort_order=3, analytics_tier=AnalyticsTier.OPERATIONS),
        # Custom quote: quotas and price are set on each clinic's subscription.
        Plan(EMPRESARIAL, "Empresarial", None, PlanLimits(), per_user, sort_order=4,
             analytics_tier=AnalyticsTier.OPERATIONS),
    ]


def default_addon_pricing() -> AddonPricing:
    return AddonPricing(
        prices={
            AddonModule.VACCINATION: _usd("10"),
            AddonModule.APPLICATIONS: _usd("15"),
            AddonModule.PROCEDURES: _usd("15"),
            AddonModule.ANALYTICS: _usd("20"),
        },
        bundle_price=_usd("29"),
    )
