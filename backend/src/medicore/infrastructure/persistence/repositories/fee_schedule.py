"""SQLAlchemy FeeScheduleRepository (prices kept as a JSONB map per doctor)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.enums import AppointmentType
from medicore.domain.shared.identifiers import FeeScheduleId, TenantId, UserId
from medicore.domain.value_objects.fee import FEE_CURRENCY
from medicore.domain.value_objects.money import Money
from medicore.infrastructure.persistence.models.fee_schedule import FeeScheduleModel


def _to_entity(row: FeeScheduleModel) -> FeeSchedule:
    schedule = FeeSchedule.__new__(FeeSchedule)  # stored data was validated when written
    schedule.id = FeeScheduleId.parse(row.id)
    schedule.tenant_id = TenantId.parse(row.tenant_id)
    schedule.doctor_id = UserId.parse(row.doctor_id)
    schedule.prices = {
        AppointmentType(kind): Money(Decimal(amount), FEE_CURRENCY)
        for kind, amount in (row.prices or {}).items()
        if kind in AppointmentType.__members__.values()
    }
    schedule.updated_at = row.updated_at
    return schedule


class SqlFeeScheduleRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(FeeScheduleModel).filter(FeeScheduleModel.tenant_id == self._tid)

    def get_by_doctor(self, doctor_id: UserId) -> FeeSchedule | None:
        row = self._q().filter(FeeScheduleModel.doctor_id == doctor_id.value).first()
        return _to_entity(row) if row else None

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, FeeSchedule]:
        if not doctor_ids:
            return {}
        rows = self._q().filter(FeeScheduleModel.doctor_id.in_([d.value for d in doctor_ids]))
        return {(s := _to_entity(r)).doctor_id: s for r in rows}

    def save(self, schedule: FeeSchedule) -> None:
        row = self._s.get(FeeScheduleModel, schedule.id.value)
        if row is None:
            row = FeeScheduleModel(id=schedule.id.value)
            self._s.add(row)
        row.tenant_id = schedule.tenant_id.value
        row.doctor_id = schedule.doctor_id.value
        row.prices = {str(k): f"{v.amount:.2f}" for k, v in schedule.prices.items()}
        row.updated_at = schedule.updated_at
