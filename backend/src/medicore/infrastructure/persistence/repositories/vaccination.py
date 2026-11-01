"""SQLAlchemy VaccinationRecordRepository."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    InjectionSite,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.shared.identifiers import (
    PatientId,
    TenantId,
    UserId,
    VaccinationRecordId,
)
from medicore.infrastructure.persistence.models.vaccination_record import VaccinationRecordModel


def to_vaccination_record(row: VaccinationRecordModel) -> VaccinationRecord:
    record = VaccinationRecord.__new__(VaccinationRecord)  # skip __post_init__ (stored data)
    record.id = VaccinationRecordId.parse(row.id)
    record.tenant_id = TenantId.parse(row.tenant_id)
    record.patient_id = PatientId.parse(row.patient_id)
    record.vaccine_code = row.vaccine_code
    record.dose_key = row.dose_key
    record.outcome = VaccinationOutcome(row.outcome)
    record.occurred_on = row.occurred_on
    record.source = VaccinationSource(row.source)
    record.recorded_by_id = UserId.parse(row.recorded_by_id)
    record.lot = row.lot
    record.route = VaccineRoute(row.route) if row.route else None
    record.site = InjectionSite(row.site) if row.site else None
    record.notes = row.notes
    record.created_at = row.created_at
    record.voided_at = row.voided_at
    record.voided_by_id = UserId.parse(row.voided_by_id) if row.voided_by_id else None
    record.void_reason = row.void_reason
    return record


class SqlVaccinationRecordRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(VaccinationRecordModel).filter(
            VaccinationRecordModel.tenant_id == self._tid
        )

    def get_by_id(self, record_id: VaccinationRecordId) -> VaccinationRecord | None:
        row = self._q().filter(VaccinationRecordModel.id == record_id.value).first()
        return to_vaccination_record(row) if row else None

    def list_by_patient(self, patient_id: PatientId) -> list[VaccinationRecord]:
        rows = (
            self._q()
            .filter(VaccinationRecordModel.patient_id == patient_id.value)
            .order_by(
                VaccinationRecordModel.occurred_on.desc(),
                VaccinationRecordModel.created_at.desc(),
            )
            .all()
        )
        return [to_vaccination_record(r) for r in rows]

    def list_active_by_patients(self, patient_ids: list[PatientId]) -> list[VaccinationRecord]:
        if not patient_ids:
            return []
        rows = (
            self._q()
            .filter(
                VaccinationRecordModel.patient_id.in_([p.value for p in patient_ids]),
                VaccinationRecordModel.voided_at.is_(None),
            )
            .all()
        )
        return [to_vaccination_record(r) for r in rows]

    def list_administered_on(self, day: date) -> list[VaccinationRecord]:
        rows = (
            self._q()
            .filter(
                VaccinationRecordModel.occurred_on == day,
                VaccinationRecordModel.voided_at.is_(None),
                VaccinationRecordModel.outcome == str(VaccinationOutcome.ADMINISTERED),
                VaccinationRecordModel.source == str(VaccinationSource.CLINIC),
            )
            .order_by(VaccinationRecordModel.created_at.desc())
            .all()
        )
        return [to_vaccination_record(r) for r in rows]

    def save(self, record: VaccinationRecord) -> None:
        row = self._s.get(VaccinationRecordModel, record.id.value)
        if row is None:
            row = VaccinationRecordModel(id=record.id.value)
            self._s.add(row)
        row.tenant_id = record.tenant_id.value
        row.patient_id = record.patient_id.value
        row.vaccine_code = record.vaccine_code
        row.dose_key = record.dose_key
        row.outcome = str(record.outcome)
        row.occurred_on = record.occurred_on
        row.source = str(record.source)
        row.lot = record.lot
        row.route = str(record.route) if record.route else None
        row.site = str(record.site) if record.site else None
        row.notes = record.notes
        row.recorded_by_id = record.recorded_by_id.value
        row.created_at = record.created_at
        row.voided_at = record.voided_at
        row.voided_by_id = record.voided_by_id.value if record.voided_by_id else None
        row.void_reason = record.void_reason
