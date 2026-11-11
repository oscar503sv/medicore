"""Subscription ports: the catalog (platform-level) and each clinic's payments."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.entities.subscription_payment import SubscriptionPayment


class PlanRepository(Protocol):
    def list(self, include_inactive: bool = True) -> list[Plan]:
        """Plans in display order."""
        ...

    def get(self, code: str) -> Plan | None: ...

    def save(self, plan: Plan) -> None: ...


class AddonPricingRepository(Protocol):
    """A single row: the current price of each add-on module and of the bundle."""

    def get(self) -> AddonPricing: ...

    def save(self, pricing: AddonPricing) -> None: ...


class SubscriptionPaymentRepository(Protocol):
    """A clinic's subscription payments (tenant-scoped)."""

    def list(self) -> list[SubscriptionPayment]:
        """Newest first (by payment date, then by when it was recorded)."""
        ...

    def save(self, payment: SubscriptionPayment) -> None: ...
