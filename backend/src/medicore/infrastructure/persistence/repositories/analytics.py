"""SQLAlchemy read model behind the clinic's metrics (tenant-scoped, read-only).

Selects only the columns the metrics aggregate (who, when, type, status, insurer, charge):
never reasons, notes or anything clinical. Aggregation happens in the application layer,
over at most a year of one clinic's appointments.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from medicore.domain.repositories._support import AppointmentFact, ProcedureFact
from medicore.domain.shared.identifiers import PatientId, TenantId, UserId
from medicore.infrastructure.persistence.models.application import ApplicationRecordModel
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.procedure import ProcedureModel
from medicore.infrastructure.persistence.models.vaccination_record import (
    VaccinationRecordModel,
)


class SqlAnalyticsReadModel:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def appointment_facts(
        self, start: datetime, end: datetime, doctor_id: UserId | None = None
    ) -> list[AppointmentFact]:
        a = AppointmentModel
        q = self._s.query(
            a.doctor_id, a.patient_id, a.type, a.status, a.scheduled_start, a.created_at,
            a.insurance_id, a.fee,
        ).filter(a.tenant_id == self._tid, a.scheduled_start >= start, a.scheduled_start < end)
        if doctor_id is not None:
            q = q.filter(a.doctor_id == doctor_id.value)
        return [
            AppointmentFact(
                doctor_id=str(r.doctor_id), patient_id=str(r.patient_id), type=r.type,
                status=r.status, scheduled_start=r.scheduled_start, created_at=r.created_at,
                insurer_id=str(r.insurance_id) if r.insurance_id else None, charged=r.fee,
            )
            for r in q.all()
        ]

    def first_visits(
        self, patient_ids: list[PatientId], doctor_id: UserId | None = None
    ) -> dict[PatientId, datetime]:
        if not patient_ids:
            return {}
        a = AppointmentModel
        q = (
            self._s.query(a.patient_id, func.min(a.scheduled_start))
            .filter(
                a.tenant_id == self._tid,
                a.status == "completed",
                a.patient_id.in_([p.value for p in patient_ids]),
            )
            .group_by(a.patient_id)
        )
        if doctor_id is not None:
            q = q.filter(a.doctor_id == doctor_id.value)
        return {PatientId.parse(pid): first for pid, first in q.all()}

    def procedure_facts(
        self, since: datetime, until: datetime, doctor_id: UserId | None = None
    ) -> list[ProcedureFact]:
        p = ProcedureModel
        q = self._s.query(p.ordered_by_id, p.performed_at, p.fee, p.fee_included).filter(
            p.tenant_id == self._tid,
            p.status == "completed",
            p.performed_at >= since,
            p.performed_at < until,
        )
        if doctor_id is not None:
            q = q.filter(p.ordered_by_id == doctor_id.value)
        return [
            ProcedureFact(
                doctor_id=str(r.ordered_by_id), performed_at=r.performed_at,
                charged=None if r.fee_included else r.fee,
            )
            for r in q.all()
        ]

    def vaccinations_recorded(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> int:
        v = VaccinationRecordModel
        q = self._s.query(func.count()).select_from(v).filter(
            v.tenant_id == self._tid, v.voided_at.is_(None),
            v.occurred_on >= first, v.occurred_on <= last,
        )
        if user_id is not None:
            q = q.filter(v.recorded_by_id == user_id.value)
        return q.scalar() or 0

    def applications_recorded(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> int:
        r = ApplicationRecordModel
        q = self._s.query(func.count()).select_from(r).filter(
            r.tenant_id == self._tid, r.voided_at.is_(None), r.outcome == "applied",
            r.recorded_at >= since, r.recorded_at < until,
        )
        if user_id is not None:
            q = q.filter(r.recorded_by_id == user_id.value)
        return q.scalar() or 0
