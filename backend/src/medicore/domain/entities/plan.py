"""Subscription catalog: the plans clinics subscribe to and the add-on module prices.

Platform-level reference data (no ``tenant_id``), edited from the platform console so
prices and quotas can change without a deploy. A clinic's subscription points at a plan
by its ``code``; what it pays is quoted from this catalog at the time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from medicore.domain.enums import CLINICAL_MODULES, AddonModule, AnalyticsTier, PlanFeature
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import PlanLimits

CURRENCY = "USD"


def _check_price(price: Money, what: str) -> None:
    if price.currency != CURRENCY:
        raise InvalidValueObject(f"{what} must be in {CURRENCY}", code="plan.invalid_price")
    if price.amount < 0:
        raise InvalidValueObject(f"{what} cannot be negative", code="plan.invalid_price")


@dataclass(slots=True)
class Plan:
    code: str  # stable identifier, e.g. "clinica"; never changes
    name: str
    # None: priced per contract ("cotización personalizada"), set on each subscription.
    monthly_price: Money | None
    limits: PlanLimits
    features: frozenset[PlanFeature] = frozenset()
    active: bool = True  # inactive plans can't be chosen for new subscriptions
    sort_order: int = 0
    analytics_tier: AnalyticsTier = AnalyticsTier.BASIC

    def __post_init__(self) -> None:
        self._validate()

    def has(self, feature: PlanFeature) -> bool:
        return feature in self.features

    def update(
        self,
        *,
        name: str,
        monthly_price: Money | None,
        limits: PlanLimits,
        features: frozenset[PlanFeature],
        active: bool,
        analytics_tier: AnalyticsTier | None = None,
    ) -> None:
        self.name = name.strip()
        self.monthly_price = monthly_price
        self.limits = limits
        self.features = features
        self.active = active
        if analytics_tier is not None:
            self.analytics_tier = analytics_tier
        self._validate()

    def _validate(self) -> None:
        if not self.name.strip():
            raise InvalidValueObject("plan name is required", code="plan.name_required")
        if self.monthly_price is not None:
            _check_price(self.monthly_price, "plan price")


@dataclass(slots=True)
class AddonPricing:
    """Monthly price of each optional module, and of the clinical modules together (the
    bundle). The analytics add-on is always charged on its own."""

    prices: dict[AddonModule, Money] = field(default_factory=dict)
    bundle_price: Money = field(default_factory=lambda: Money(Decimal("0"), CURRENCY))

    def __post_init__(self) -> None:
        self._validate()

    def price_of(self, module: AddonModule) -> Money:
        return self.prices[module]

    def monthly_price(self, modules: frozenset[AddonModule]) -> Money:
        """What the given modules cost a month. All the clinical modules together get the
        bundle price (or their plain sum, should the bundle ever be configured above it);
        the others add their own price."""
        clinical = self._sum(modules & CLINICAL_MODULES)
        if modules >= CLINICAL_MODULES and self.bundle_price.amount < clinical.amount:
            clinical = self.bundle_price
        return clinical + self._sum(modules - CLINICAL_MODULES)

    def _sum(self, modules: frozenset[AddonModule]) -> Money:
        total = Money(Decimal("0"), CURRENCY)
        for module in modules:
            total = total + self.prices[module]
        return total

    def update(self, prices: dict[AddonModule, Money], bundle_price: Money) -> None:
        self.prices = dict(prices)
        self.bundle_price = bundle_price
        self._validate()

    def _validate(self) -> None:
        missing = set(AddonModule) - set(self.prices)
        if missing:
            raise InvalidValueObject(
                f"missing price for {sorted(missing)}", code="plan.invalid_price"
            )
        for module, price in self.prices.items():
            _check_price(price, f"{module} price")
        _check_price(self.bundle_price, "bundle price")
