"""Consultation and procedure fees: the price a clinic lists and what one visit is charged.

Fees are in US dollars (the currency of El Salvador) with cents. Each appointment and
procedure keeps a copy of the price in force when it was booked or ordered (``listed``)
next to what it is actually charged (``charged``), so changing a price later never rewrites
past income, and a discount or a courtesy shows up as the gap between the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.money import Money

FEE_CURRENCY = "USD"
MAX_FEE = Decimal("10000")
NOTE_MAX = 200
ZERO = Money(Decimal("0.00"), FEE_CURRENCY)


def fee(amount: Decimal | int | str) -> Money:
    """A fee amount: dollars with at most two decimals, from 0 to MAX_FEE."""
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0 or value > MAX_FEE:
        raise InvalidValueObject(f"invalid fee {amount}", code="fee.invalid_amount")
    if value != value.quantize(Decimal("0.01")):
        raise InvalidValueObject(f"a fee has at most two decimals: {amount}",
                                 code="fee.invalid_amount")
    return Money(value.quantize(Decimal("0.01")), FEE_CURRENCY)


def check_fee(value: Money | None) -> None:
    """Validate a fee already built as Money (None means "no price")."""
    if value is not None:
        if value.currency != FEE_CURRENCY:
            raise InvalidValueObject("fees are in USD", code="fee.invalid_amount")
        fee(value.amount)


@dataclass(frozen=True, slots=True)
class Charge:
    """What a visit costs: the listed price at the time, what is charged, and why they
    differ. ``listed`` is None when no price was set; ``charged`` follows it until someone
    adjusts it."""

    listed: Money | None = None
    charged: Money | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        check_fee(self.listed)
        check_fee(self.charged)
        note = (self.note or "").strip() or None
        if note is not None and len(note) > NOTE_MAX:
            raise InvalidValueObject("the note is too long", code="fee.note_too_long")
        object.__setattr__(self, "note", note)

    @classmethod
    def at_list_price(cls, listed: Money | None) -> Charge:
        return cls(listed=listed, charged=listed)

    @property
    def adjusted(self) -> bool:
        return self.charged != self.listed

    def adjust(self, charged: Money, note: str | None) -> Charge:
        """Charge a different amount. Moving away from a listed price needs a reason
        ("courtesy", "senior discount") so the gap can be explained later."""
        result = Charge(listed=self.listed, charged=charged, note=note)
        if self.listed is not None and charged != self.listed and result.note is None:
            raise InvalidValueObject("say why the fee differs from the listed price",
                                     code="fee.note_required")
        return result
