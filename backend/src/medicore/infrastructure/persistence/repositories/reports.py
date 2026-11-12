"""SQLAlchemy read model behind the clinic's reports (tenant-scoped, read-only).

Each query joins the patient for the name, code and (appointments only) phone, and selects
just the columns a report exports: never reasons, notes or anything clinical.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from medicore.domain.repositories._support import (
    ApplicationReportRow,
    AppointmentReportRow,
    ProcedureReportRow,
    VaccinationReportRow,
)
from medicore.domain.shared.identifiers import TenantId, UserId
from medicore.infrastructure.persistence.models.application import (
    ApplicationOrderModel,
    ApplicationRecordModel,
)
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.procedure import ProcedureModel
from medicore.infrastructure.persistence.models.vaccination_record import (
    VaccinationRecordModel,
)


def _name(first: str, last: str) -> str:
    return f"{first} {last}".strip()


class SqlReportReadModel:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def appointment_rows(
        self, start: datetime, end: datetime, user_id: UserId | None = None
    ) -> list[AppointmentReportRow]:
        a, p = AppointmentModel, PatientModel
        q = (
            self._s.query(
                a.code, a.scheduled_start, a.doctor_id, a.type, a.status, a.insurance_id,
                a.listed_fee, a.fee, a.fee_note,
                p.code.label("patient_code"), p.first_name, p.last_name,
                p.contact["phone"].astext.label("phone"),
            )
            .join(p, p.id == a.patient_id)
            .filter(a.tenant_id == self._tid, a.scheduled_start >= start,
                    a.scheduled_start < end)
            .order_by(a.scheduled_start, a.code)
        )
        if user_id is not None:
            q = q.filter(a.doctor_id == user_id.value)
        return [
            AppointmentReportRow(
                code=r.code, scheduled_start=r.scheduled_start, patient_code=r.patient_code,
                patient_name=_name(r.first_name, r.last_name), patient_phone=r.phone or None,
                doctor_id=str(r.doctor_id), type=r.type, status=r.status,
                insurer_id=str(r.insurance_id) if r.insurance_id else None,
                listed=r.listed_fee, charged=r.fee, fee_note=r.fee_note,
            )
            for r in q.all()
        ]

    def procedure_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ProcedureReportRow]:
        pr, p = ProcedureModel, PatientModel
        q = (
            self._s.query(
                pr.type_name, pr.performed_at, pr.ordered_by_id, pr.performed_by_id,
                pr.listed_fee, pr.fee, pr.fee_included,
                p.code.label("patient_code"), p.first_name, p.last_name,
            )
            .join(p, p.id == pr.patient_id)
            .filter(pr.tenant_id == self._tid, pr.status == "completed",
                    pr.performed_at >= since, pr.performed_at < until)
            .order_by(pr.performed_at)
        )
        if user_id is not None:
            q = q.filter(pr.ordered_by_id == user_id.value)
        return [
            ProcedureReportRow(
                type_name=r.type_name, performed_at=r.performed_at,
                patient_code=r.patient_code, patient_name=_name(r.first_name, r.last_name),
                ordered_by_id=str(r.ordered_by_id),
                performed_by_id=str(r.performed_by_id) if r.performed_by_id else None,
                listed=r.listed_fee, charged=None if r.fee_included else r.fee,
                included=bool(r.fee_included),
            )
            for r in q.all()
        ]

    def vaccination_rows(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> list[VaccinationReportRow]:
        v, p = VaccinationRecordModel, PatientModel
        q = (
            self._s.query(
                v.occurred_on, v.vaccine_code, v.dose_key, v.lot, v.recorded_by_id,
                p.code.label("patient_code"), p.first_name, p.last_name, p.sex,
                p.date_of_birth,
            )
            .join(p, p.id == v.patient_id)
            .filter(v.tenant_id == self._tid, v.voided_at.is_(None),
                    v.outcome == "administered", v.source == "clinic",
                    v.occurred_on >= first, v.occurred_on <= last)
            .order_by(v.occurred_on, v.created_at)
        )
        if user_id is not None:
            q = q.filter(v.recorded_by_id == user_id.value)
        return [
            VaccinationReportRow(
                occurred_on=r.occurred_on, patient_code=r.patient_code,
                patient_name=_name(r.first_name, r.last_name), patient_sex=r.sex,
                date_of_birth=r.date_of_birth, vaccine_code=r.vaccine_code,
                dose_key=r.dose_key, lot=r.lot, recorded_by_id=str(r.recorded_by_id),
            )
            for r in q.all()
        ]

    def application_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ApplicationReportRow]:
        r, o, p = ApplicationRecordModel, ApplicationOrderModel, PatientModel
        q = (
            self._s.query(
                r.recorded_at, r.dose_number, r.lot, r.recorded_by_id,
                o.drug, o.dose, o.route,
                p.code.label("patient_code"), p.first_name, p.last_name,
            )
            .join(o, o.id == r.order_id)
            .join(p, p.id == r.patient_id)
            .filter(r.tenant_id == self._tid, r.voided_at.is_(None), r.outcome == "applied",
                    r.recorded_at >= since, r.recorded_at < until)
            .order_by(r.recorded_at)
        )
        if user_id is not None:
            q = q.filter(r.recorded_by_id == user_id.value)
        return [
            ApplicationReportRow(
                recorded_at=x.recorded_at, patient_code=x.patient_code,
                patient_name=_name(x.first_name, x.last_name), drug=x.drug, dose=x.dose,
                route=x.route, dose_number=x.dose_number, lot=x.lot,
                recorded_by_id=str(x.recorded_by_id),
            )
            for x in q.all()
        ]
