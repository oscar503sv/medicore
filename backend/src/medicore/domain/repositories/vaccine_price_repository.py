"""VaccinePriceRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.vaccine_price import VaccinePrice
from medicore.domain.value_objects.money import Money


class VaccinePriceRepository(Protocol):
    def list(self) -> list[VaccinePrice]: ...

    def as_map(self) -> dict[str, Money]:
        """The clinic's prices by vaccine code, in one read."""
        ...

    def get_for_update(self, vaccine_code: str) -> VaccinePrice | None:
        """The vaccine's price, locking its row so concurrent edits queue up."""
        ...

    def save(self, price: VaccinePrice) -> None:
        """Insert or replace the vaccine's price (atomic, no lock needed)."""
        ...

    def delete(self, vaccine_code: str) -> None: ...
