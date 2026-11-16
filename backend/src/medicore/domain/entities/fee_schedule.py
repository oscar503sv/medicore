"""FeeSchedule aggregate: what a doctor charges for each kind of appointment.

One per doctor. Procedure and vaccination appointments are not priced here: what they cost
depends on which procedure or vaccine is given, so it comes from a catalog. A type without a
price simply has none (the booking then shows "no fee set").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import AppointmentType
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import FeeScheduleId, TenantId, UserId
from medicore.domain.value_objects.fee import check_fee
from medicore.domain.value_objects.money import Money

CATALOG_PRICED_TYPES = frozenset({AppointmentType.PROCEDURE, AppointmentType.VACCINATION})
PRICED_TYPES: tuple[AppointmentType, ...] = tuple(
    t for t in AppointmentType if t not in CATALOG_PRICED_TYPES
)


@dataclass(slots=True)
class FeeSchedule:
    id: FeeScheduleId
    tenant_id: TenantId
    doctor_id: UserId
    prices: dict[AppointmentType, Money] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _check(self.prices)

    def price_for(self, kind: AppointmentType) -> Money | None:
        return self.prices.get(kind)

    def set_prices(self, prices: dict[AppointmentType, Money], now: datetime) -> None:
        """Replace every price (a type left out has no price)."""
        _check(prices)
        self.prices = dict(prices)
        self.updated_at = now


def _check(prices: dict[AppointmentType, Money]) -> None:
    for kind, price in prices.items():
        if kind not in PRICED_TYPES:
            raise InvalidValueObject("procedures and vaccinations are priced from a catalog",
                                     code="fee.procedure_from_catalog")
        check_fee(price)
