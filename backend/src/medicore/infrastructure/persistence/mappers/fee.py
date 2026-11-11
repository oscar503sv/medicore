"""Fees in columns: a ``Charge`` as (listed, charged, note) and a price as a Numeric."""

from __future__ import annotations

from decimal import Decimal

from medicore.domain.value_objects.fee import FEE_CURRENCY, Charge
from medicore.domain.value_objects.money import Money


def money_from(amount: Decimal | None) -> Money | None:
    return None if amount is None else Money(Decimal(amount), FEE_CURRENCY)


def amount_of(value: Money | None) -> Decimal | None:
    return None if value is None else value.amount


def charge_from(listed: Decimal | None, charged: Decimal | None, note: str | None) -> Charge:
    charge = Charge.__new__(Charge)  # stored data was validated when written
    object.__setattr__(charge, "listed", money_from(listed))
    object.__setattr__(charge, "charged", money_from(charged))
    object.__setattr__(charge, "note", note)
    return charge


def charge_columns(charge: Charge) -> tuple[Decimal | None, Decimal | None, str | None]:
    return amount_of(charge.listed), amount_of(charge.charged), charge.note
