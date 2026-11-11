"""Subscription catalog ports (platform-level, not tenant-scoped)."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.plan import AddonPricing, Plan


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
