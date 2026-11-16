"""What a vaccine dose costs.

A dose given at the clinic comes either from the clinic's own stock (private: charged at the
clinic's price) or from the health ministry (MINSAL), which is free of charge by law, also in
a private clinic (Ley de Vacunas, Decreto 1013, arts. 5, 12, 13 and 26). A private dose of a
vaccine the clinic has not priced cannot be charged, so it is refused rather than given away.
"""

from __future__ import annotations

from collections.abc import Iterable

from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import VaccineSupply
from medicore.domain.shared.errors import DomainError
from medicore.domain.value_objects.fee import ZERO
from medicore.domain.value_objects.money import Money


class VaccinePriceMissing(DomainError):
    """A private dose of a vaccine the clinic has not priced."""

    code = "vaccination.price_missing"

    def __init__(self, vaccine_code: str) -> None:
        super().__init__(f"the clinic has no price for vaccine {vaccine_code}",
                         vaccine=vaccine_code)


def dose_fee(vaccine_code: str, supply: VaccineSupply, price: Money | None) -> Money:
    if supply == VaccineSupply.MINSAL:
        return ZERO
    if price is None:
        raise VaccinePriceMissing(vaccine_code)
    return price


def doses_total(records: Iterable[VaccinationRecord]) -> Money:
    """The sum of the copied prices of the standing (not voided) priced doses."""
    total = ZERO
    for r in records:
        if not r.is_voided and r.listed_fee is not None:
            total = total + r.listed_fee
    return total
