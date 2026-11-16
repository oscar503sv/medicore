"""SQLAlchemy VaccinePriceRepository."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from medicore.domain.entities.vaccine_price import VaccinePrice
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.fee import FEE_CURRENCY
from medicore.domain.value_objects.money import Money
from medicore.infrastructure.persistence.models.vaccine_price import VaccinePriceModel


def _to_entity(row: VaccinePriceModel) -> VaccinePrice:
    price = VaccinePrice.__new__(VaccinePrice)  # stored data was validated when written
    object.__setattr__(price, "tenant_id", TenantId.parse(row.tenant_id))
    object.__setattr__(price, "vaccine_code", row.vaccine_code)
    object.__setattr__(price, "price", Money(row.price, FEE_CURRENCY))
    object.__setattr__(price, "updated_at", row.updated_at)
    return price


class SqlVaccinePriceRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(VaccinePriceModel).filter(VaccinePriceModel.tenant_id == self._tid)

    def list(self) -> list[VaccinePrice]:
        return [_to_entity(r) for r in self._q().order_by(VaccinePriceModel.vaccine_code)]

    def get_for_update(self, vaccine_code: str) -> VaccinePrice | None:
        row = (
            self._q()
            .filter(VaccinePriceModel.vaccine_code == vaccine_code)
            .with_for_update()
            .populate_existing()
            .first()
        )
        return _to_entity(row) if row else None

    def as_map(self) -> dict[str, Money]:
        return {p.vaccine_code: p.price for p in self.list()}

    def save(self, price: VaccinePrice) -> None:
        stmt = insert(VaccinePriceModel).values(
            tenant_id=self._tid, vaccine_code=price.vaccine_code,
            price=price.price.amount, updated_at=price.updated_at,
        )
        self._s.execute(stmt.on_conflict_do_update(
            index_elements=["tenant_id", "vaccine_code"],
            set_={"price": stmt.excluded.price, "updated_at": stmt.excluded.updated_at},
        ))

    def delete(self, vaccine_code: str) -> None:
        self._s.execute(delete(VaccinePriceModel).where(
            VaccinePriceModel.tenant_id == self._tid,
            VaccinePriceModel.vaccine_code == vaccine_code,
        ))
