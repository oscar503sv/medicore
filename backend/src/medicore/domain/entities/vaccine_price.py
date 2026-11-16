"""VaccinePrice: what a clinic charges for one privately supplied vaccine.

One per clinic and vaccine; a vaccine without a price simply has no row. Vaccines supplied by
the health ministry (MINSAL) are never priced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from medicore.domain.services.immunization import VACCINES
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.fee import check_fee
from medicore.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class VaccinePrice:
    tenant_id: TenantId
    vaccine_code: str
    price: Money
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.vaccine_code not in VACCINES:
            raise InvalidValueObject(
                f"unknown vaccine {self.vaccine_code!r}", code="vaccine_price.unknown_vaccine"
            )
        check_fee(self.price)
