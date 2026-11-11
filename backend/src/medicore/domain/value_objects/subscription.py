"""A clinic's subscription: plan, contracted modules and the period it is paid (or on
trial) until. Activation and renewal are manual (bank transfer), done from the console."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date, timedelta

from medicore.domain.enums import AddonModule, SubscriptionStatus
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides

DEFAULT_GRACE_DAYS = 7
DEFAULT_TRIAL_DAYS = 7
MAX_RENEWAL_MONTHS = 24


def add_months(day: date, months: int) -> date:
    """Same day ``months`` later, clamped to the month's end (31 Jan + 1 → 28/29 Feb)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True, slots=True)
class Subscription:
    plan_code: str
    modules: frozenset[AddonModule] = frozenset()
    # Last day covered (paid or on trial). None: open-ended, e.g. the public demo clinics.
    period_end: date | None = None
    is_trial: bool = False
    # Days after period_end the clinic keeps working before turning read-only.
    grace_days: int = DEFAULT_GRACE_DAYS
    # Per-clinic exceptions: custom quotas and price (Empresarial, or a special deal).
    limit_overrides: LimitOverrides | None = None
    price_override: Money | None = None

    def __post_init__(self) -> None:
        if not self.plan_code:
            raise InvalidValueObject("subscription needs a plan", code="plan.required")
        if self.grace_days < 0:
            raise InvalidValueObject("grace days cannot be negative", code="plan.invalid_grace")
        if self.price_override is not None and self.price_override.amount < 0:
            raise InvalidValueObject("price cannot be negative", code="plan.invalid_price")
        if self.limit_overrides is not None and self.limit_overrides.is_empty:
            object.__setattr__(self, "limit_overrides", None)

    def status(self, today: date) -> SubscriptionStatus:
        if self.period_end is None or today <= self.period_end:
            return SubscriptionStatus.TRIAL if self.is_trial else SubscriptionStatus.ACTIVE
        # A trial that ends is not a lapsed payment: no grace period.
        grace = 0 if self.is_trial else self.grace_days
        if today <= self.period_end + timedelta(days=grace):
            return SubscriptionStatus.GRACE
        return SubscriptionStatus.READ_ONLY

    @property
    def grace_until(self) -> date | None:
        """Last day the clinic keeps working after the period ends (a trial gets no grace)."""
        if self.period_end is None:
            return None
        return self.period_end + timedelta(days=0 if self.is_trial else self.grace_days)

    def renew(self, today: date, months: int) -> Subscription:
        """A paid renewal of ``months`` months. A clinic that is up to date (or within its
        grace days, which it used) continues from its paid-until date; a lapsed clinic, a
        trial that ended or an open-ended one starts from today."""
        if not 1 <= months <= MAX_RENEWAL_MONTHS:
            raise InvalidValueObject(
                f"a renewal covers 1 to {MAX_RENEWAL_MONTHS} months", code="payment.invalid_months",
                max=MAX_RENEWAL_MONTHS,
            )
        continuing = self.period_end is not None and self.status(today) in (
            SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL, SubscriptionStatus.GRACE,
        )
        # period_end is the last covered day, so a fresh period starts "after yesterday".
        base = self.period_end if continuing else today - timedelta(days=1)
        return replace(self, is_trial=False, period_end=add_months(base, months))

    def days_left(self, today: date) -> int | None:
        """Days until the period ends (negative once it has); None when open-ended."""
        return None if self.period_end is None else (self.period_end - today).days

    def has_module(self, module: AddonModule) -> bool:
        return module in self.modules

    def start_trial(self, today: date, days: int = DEFAULT_TRIAL_DAYS) -> Subscription:
        if days < 1:
            raise InvalidValueObject("a trial lasts at least one day", code="plan.invalid_trial")
        return replace(self, is_trial=True, period_end=today + timedelta(days=days - 1))
