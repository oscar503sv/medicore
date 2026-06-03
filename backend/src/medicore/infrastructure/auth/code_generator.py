"""DB-backed sequential code generator with per-tenant counters and pessimistic locking."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from medicore.domain.enums import RecordType
from medicore.infrastructure.persistence.models.counters import TenantCounterModel

_RECORD_SUFFIX = {
    RecordType.EVOLUTION: "EV",
    RecordType.EMERGENCY_NOTE: "UR",
    RecordType.PROCEDURE_NOTE: "PR",
    RecordType.SURGICAL_NOTE: "QX",
    RecordType.LAB_REPORT: "LR",
    RecordType.IMAGING_REPORT: "IM",
    RecordType.DIAGNOSIS: "DX",
    RecordType.PRESCRIPTION_NOTE: "RX",
    RecordType.VACCINATION: "VA",
    RecordType.REFERRAL: "RF",
    RecordType.DISCHARGE_SUMMARY: "EP",
    RecordType.NURSING_NOTE: "EF",
    RecordType.GENERIC: "GN",
}


class DbSequentialCodeGenerator:
    """Increments a per-tenant counter inside the current session transaction.

    Uses SELECT FOR UPDATE so concurrent requests get unique values.
    The caller's UoW commits the transaction after all domain changes — the counter
    increment is part of the same atomic write.
    """

    def __init__(self, session: Session, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _next(self, series: str) -> int:
        row = (
            self._session.query(TenantCounterModel)
            .filter(
                TenantCounterModel.tenant_id == self._tenant_id,
                TenantCounterModel.series == series,
            )
            .with_for_update()
            .first()
        )
        if row is None:
            row = TenantCounterModel(
                tenant_id=self._tenant_id, series=series, last_value=0
            )
            self._session.add(row)
            self._session.flush()
        row.last_value += 1
        return row.last_value

    def next_patient_code(self) -> str:
        n = self._next("patient")
        return f"P-{n:05d}"

    def next_appointment_code(self) -> str:
        n = self._next("appointment")
        return f"A-{n}"

    def next_record_code(self, record_type: RecordType, on: date) -> str:
        n = self._next("record")
        suffix = _RECORD_SUFFIX.get(record_type, "GN")
        return f"REC-{on.year}-{on.month:02d}{on.day:02d}-{suffix}-{n}"
