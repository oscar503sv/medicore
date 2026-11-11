"""What a clinic pays a month: its plan plus contracted modules, unless a custom price
was agreed for it."""

from __future__ import annotations

from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.subscription import Subscription


def monthly_quote(subscription: Subscription, plan: Plan, addons: AddonPricing) -> Money | None:
    """None when there is nothing to quote from: a custom-quote plan without an agreed
    price on the subscription."""
    if subscription.price_override is not None:
        return subscription.price_override
    if plan.monthly_price is None:
        return None
    return plan.monthly_price + addons.monthly_price(subscription.modules)
