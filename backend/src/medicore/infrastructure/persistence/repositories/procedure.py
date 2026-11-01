"""SQLAlchemy ProcedureRepository.

Column names match the entity fields one to one (like the applications repository); the
amendments, a list of value objects, are stored as JSONB.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from medicore.domain.entities.procedure import Procedure, ProcedureAmendment, ProcedureType
from medicore.domain.enums import ProcedurePerformer, ProcedureSource, ProcedureStatus
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    Identifier,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
    TenantId,
    UserId,
)
from medicore.infrastructure.persistence.models.procedure import ProcedureModel, ProcedureTypeModel


def _amendments_from(rows: list[dict]) -> list[ProcedureAmendment]:
    return [
        ProcedureAmendment(at=datetime.fromisoformat(a["at"]), by_id=UserId.parse(a["by_id"]),
                           text=a["text"], reason=a["reason"])
        for a in rows or []
    ]


def _amendments_to(items: list[ProcedureAmendment]) -> list[dict]:
    return [{"at": a.at.isoformat(), "by_id": str(a.by_id), "text": a.text, "reason": a.reason}
            for a in items]


# Field → how to rebuild it from the column (anything not listed is stored as-is).
_TYPE_TYPES: dict[str, Any] = {
    "id": ProcedureTypeId, "tenant_id": TenantId, "performer": ProcedurePerformer,
}
_PROCEDURE_TYPES: dict[str, Any] = {
    "id": ProcedureId, "tenant_id": TenantId, "patient_id": PatientId, "type_id": ProcedureTypeId,
    "performer": ProcedurePerformer, "source": ProcedureSource, "status": ProcedureStatus,
    "ordered_by_id": UserId, "created_by_id": UserId, "consultation_id": ConsultationId,
    "appointment_id": AppointmentId, "consent_by_id": UserId, "performed_by_id": UserId,
    "cancelled_by_id": UserId, "amendments": _amendments_from,
}


def _load(cls, row, types: dict[str, Any]):
    obj = cls.__new__(cls)  # skip __post_init__: stored data was validated when written
    for f in fields(cls):
        value = getattr(row, f.name)
        kind = types.get(f.name)
        if kind is _amendments_from:
            value = kind(value)
        elif value is not None and kind is not None:
            value = kind.parse(value) if issubclass(kind, Identifier) else kind(value)
        setattr(obj, f.name, value)
    return obj


def _dump(obj, row) -> None:
    for f in fields(obj):
        value = getattr(obj, f.name)
        if f.name == "amendments":
            value = _amendments_to(value)
        elif isinstance(value, Identifier | Enum):
            value = value.value
        setattr(row, f.name, value)


class SqlProcedureRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _types(self):
        return self._s.query(ProcedureTypeModel).filter(ProcedureTypeModel.tenant_id == self._tid)

    def _procedures(self):
        return self._s.query(ProcedureModel).filter(ProcedureModel.tenant_id == self._tid)

    def _many(self, query) -> list[Procedure]:
        return [_load(Procedure, r, _PROCEDURE_TYPES) for r in query.all()]

    # ── catalog ──
    def get_type(self, type_id: ProcedureTypeId) -> ProcedureType | None:
        row = self._types().filter(ProcedureTypeModel.id == type_id.value).first()
        return _load(ProcedureType, row, _TYPE_TYPES) if row else None

    def list_types(self) -> list[ProcedureType]:
        rows = self._types().order_by(ProcedureTypeModel.name).all()
        return [_load(ProcedureType, r, _TYPE_TYPES) for r in rows]

    def save_type(self, kind: ProcedureType) -> None:
        row = self._s.get(ProcedureTypeModel, kind.id.value)
        if row is None:
            row = ProcedureTypeModel(id=kind.id.value)
            self._s.add(row)
        _dump(kind, row)

    # ── procedures ──
    def get(self, procedure_id: ProcedureId) -> Procedure | None:
        row = self._procedures().filter(ProcedureModel.id == procedure_id.value).first()
        return _load(Procedure, row, _PROCEDURE_TYPES) if row else None

    def list_by_patient(self, patient_id: PatientId) -> list[Procedure]:
        return self._many(
            self._procedures()
            .filter(ProcedureModel.patient_id == patient_id.value)
            .order_by(ProcedureModel.created_at.desc())
        )

    def list_open(self) -> list[Procedure]:
        open_ = [str(ProcedureStatus.PENDING), str(ProcedureStatus.IN_PROGRESS)]
        return self._many(
            self._procedures()
            .filter(ProcedureModel.status.in_(open_))
            .order_by(ProcedureModel.created_at)
        )

    def list_by_appointments(self, appointment_ids: list[AppointmentId]) -> list[Procedure]:
        if not appointment_ids:
            return []
        return self._many(
            self._procedures().filter(
                ProcedureModel.appointment_id.in_([a.value for a in appointment_ids])
            )
        )

    def list_completed_between(self, start: datetime, end: datetime) -> list[Procedure]:
        return self._many(
            self._procedures()
            .filter(
                ProcedureModel.status == str(ProcedureStatus.COMPLETED),
                ProcedureModel.performed_at >= start,
                ProcedureModel.performed_at < end,
            )
            .order_by(ProcedureModel.performed_at.desc())
        )

    def save(self, procedure: Procedure) -> None:
        row = self._s.get(ProcedureModel, procedure.id.value)
        if row is None:
            row = ProcedureModel(id=procedure.id.value)
            self._s.add(row)
        _dump(procedure, row)
