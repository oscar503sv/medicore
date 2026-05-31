"""Money value object (for future billing)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class Money:
    """A monetary amount in a given ISO-4217 currency."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise InvalidValueObject(f"currency must be a 3-letter code, got {self.currency!r}")
        object.__setattr__(self, "currency", self.currency.upper())

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise InvalidValueObject(
                f"cannot operate on different currencies: {self.currency} vs {other.currency}"
            )
