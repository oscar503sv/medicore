"""A payment a clinic made for its subscription (bank transfer, recorded by hand).

Payments are the history behind each renewal: what was paid, when, for how many months and
up to which date it left the clinic covered. Immutable once recorded; a mistake is fixed by
adjusting the subscription from the console, not by editing the payment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from medicore.domain.entities.plan import CURRENCY
from medicore.domain.enums import PaymentMethod
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import PlatformAdminId, SubscriptionPaymentId, TenantId
from medicore.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class SubscriptionPayment:
    id: SubscriptionPaymentId
    tenant_id: TenantId
    amount: Money
    paid_on: date
    months: int
    plan_code: str  # the plan paid for, kept even if the clinic changes plan later
    period_end: date  # paid-until date this payment left the clinic with
    method: PaymentMethod
    recorded_by: PlatformAdminId
    recorded_at: datetime
    reference: str | None = None  # bank reference / receipt number
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.amount.currency != CURRENCY or self.amount.amount < 0:
            raise InvalidValueObject("invalid payment amount", code="payment.invalid_amount")
        if self.months < 1:
            raise InvalidValueObject("a payment covers at least a month",
                                     code="payment.invalid_months")
