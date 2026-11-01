"""SQLAlchemy ApplicationRepository.

Column names match the entity fields one to one, so rows are mapped field by field with a
converter per kind of value (ids, enums, plain values).
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOrderStatus,
    ApplicationOutcome,
    ApplicationRoute,
    ApplicationSite,
)
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    ConsultationId,
    Identifier,
    PatientId,
    TenantId,
    UserId,
)
from medicore.infrastructure.persistence.models.application import (
    ApplicationOrderModel,
    ApplicationRecordModel,
)

# Field → how to rebuild it from the column (anything not listed is stored as-is).
_ORDER_TYPES: dict[str, Any] = {
    "id": ApplicationOrderId, "tenant_id": TenantId, "patient_id": PatientId,
    "created_by_id": UserId, "ordered_by_id": UserId, "consultation_id": ConsultationId,
    "cancelled_by_id": UserId, "route": ApplicationRoute, "source": ApplicationOrderSource,
    "status": ApplicationOrderStatus,
}
_RECORD_TYPES: dict[str, Any] = {
    "id": ApplicationRecordId, "tenant_id": TenantId, "order_id": ApplicationOrderId,
    "patient_id": PatientId, "recorded_by_id": UserId, "observation_closed_by_id": UserId,
    "voided_by_id": UserId, "outcome": ApplicationOutcome, "site": ApplicationSite,
}


def _load(cls, row, types: dict[str, Any]):
    obj = cls.__new__(cls)  # skip __post_init__: stored data was validated when written
    for f in fields(cls):
        value = getattr(row, f.name)
        kind = types.get(f.name)
        if value is not None and kind is not None:
            value = kind.parse(value) if issubclass(kind, Identifier) else kind(value)
        setattr(obj, f.name, value)
    return obj


def _dump(obj, row) -> None:
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, Identifier | Enum):
            value = value.value
        setattr(row, f.name, value)


class SqlApplicationRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _orders(self):
        return self._s.query(ApplicationOrderModel).filter(
            ApplicationOrderModel.tenant_id == self._tid
        )

    def _records(self):
        return self._s.query(ApplicationRecordModel).filter(
            ApplicationRecordModel.tenant_id == self._tid
        )

    # ── orders ──
    def get_order(self, order_id: ApplicationOrderId) -> ApplicationOrder | None:
        row = self._orders().filter(ApplicationOrderModel.id == order_id.value).first()
        return _load(ApplicationOrder, row, _ORDER_TYPES) if row else None

    def list_orders_by_patient(self, patient_id: PatientId) -> list[ApplicationOrder]:
        rows = (
            self._orders()
            .filter(ApplicationOrderModel.patient_id == patient_id.value)
            .order_by(ApplicationOrderModel.created_at.desc())
            .all()
        )
        return [_load(ApplicationOrder, r, _ORDER_TYPES) for r in rows]

    def list_open_orders(self) -> list[ApplicationOrder]:
        open_ = [str(ApplicationOrderStatus.PENDING), str(ApplicationOrderStatus.IN_PROGRESS)]
        rows = (
            self._orders()
            .filter(ApplicationOrderModel.status.in_(open_))
            .order_by(ApplicationOrderModel.starts_at)
            .all()
        )
        return [_load(ApplicationOrder, r, _ORDER_TYPES) for r in rows]

    def save_order(self, order: ApplicationOrder) -> None:
        row = self._s.get(ApplicationOrderModel, order.id.value)
        if row is None:
            row = ApplicationOrderModel(id=order.id.value)
            self._s.add(row)
        _dump(order, row)

    # ── records ──
    def get_record(self, record_id: ApplicationRecordId) -> ApplicationRecord | None:
        row = self._records().filter(ApplicationRecordModel.id == record_id.value).first()
        return _load(ApplicationRecord, row, _RECORD_TYPES) if row else None

    def list_records_by_orders(
        self, order_ids: list[ApplicationOrderId]
    ) -> list[ApplicationRecord]:
        if not order_ids:
            return []
        rows = (
            self._records()
            .filter(ApplicationRecordModel.order_id.in_([o.value for o in order_ids]))
            .order_by(ApplicationRecordModel.recorded_at)
            .all()
        )
        return [_load(ApplicationRecord, r, _RECORD_TYPES) for r in rows]

    def list_records_between(self, start: datetime, end: datetime) -> list[ApplicationRecord]:
        rows = (
            self._records()
            .filter(
                ApplicationRecordModel.recorded_at >= start,
                ApplicationRecordModel.recorded_at < end,
                ApplicationRecordModel.voided_at.is_(None),
            )
            .order_by(ApplicationRecordModel.recorded_at.desc())
            .all()
        )
        return [_load(ApplicationRecord, r, _RECORD_TYPES) for r in rows]

    def list_observing(self) -> list[ApplicationRecord]:
        rows = (
            self._records()
            .filter(
                ApplicationRecordModel.observe_until.is_not(None),
                ApplicationRecordModel.observation_closed_at.is_(None),
                ApplicationRecordModel.voided_at.is_(None),
            )
            .order_by(ApplicationRecordModel.observe_until)
            .all()
        )
        return [_load(ApplicationRecord, r, _RECORD_TYPES) for r in rows]

    def save_record(self, record: ApplicationRecord) -> None:
        row = self._s.get(ApplicationRecordModel, record.id.value)
        if row is None:
            row = ApplicationRecordModel(id=record.id.value)
            self._s.add(row)
        _dump(record, row)
