"""Which analytics tier a clinic gets: its plan's, raised to operations by the add-on."""

from __future__ import annotations

from medicore.domain.entities.plan import Plan
from medicore.domain.enums import AddonModule, AnalyticsTier
from medicore.domain.value_objects.subscription import Subscription

ADDON_TIER = AnalyticsTier.OPERATIONS


def analytics_tier(plan: Plan, subscription: Subscription) -> AnalyticsTier:
    if subscription.has_module(AddonModule.ANALYTICS) and not plan.analytics_tier.includes(
        ADDON_TIER
    ):
        return ADDON_TIER
    return plan.analytics_tier


def addon_adds_nothing(plan: Plan) -> bool:
    """A plan that already reaches the add-on's tier gains nothing from buying it."""
    return plan.analytics_tier.includes(ADDON_TIER)
