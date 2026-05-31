"""SQLAlchemy PatientRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.patient import Patient
from medicore.domain.repositories._support import Page, Paging, PatientFilter
from medicore.domain.shared.identifiers import PatientId, TenantId
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.infrastructure.persistence.mappers.entities import to_patient
from medicore.infrastructure.persistence.models.patient import PatientModel


def _contact_to_json(c: ContactInfo) -> dict:
    return {
        "phone": c.phone,
        "email": c.email,
        "address": c.address,
        "emergency_contact_name": c.emergency_contact_name,
        "emergency_contact_phone": c.emergency_contact_phone,
    }


class SqlPatientRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(PatientModel).filter(PatientModel.tenant_id == self._tid)

    def get_by_id(self, patient_id: PatientId) -> Patient | None:
        row = self._q().filter(PatientModel.id == patient_id.value).first()
        return to_patient(row) if row else None

    def list(
        self, filter: PatientFilter | None = None, paging: Paging | None = None
    ) -> Page[Patient]:
        q = self._q().order_by(PatientModel.last_name, PatientModel.first_name)
        if filter and filter.status:
            q = q.filter(PatientModel.status == filter.status)
        if filter and filter.doctor_id:
            from uuid import UUID
            q = q.filter(PatientModel.primary_doctor_id == UUID(filter.doctor_id))
        total = q.count()
        pg = paging or Paging()
        rows = q.offset(pg.offset).limit(pg.limit).all()
        return Page(
            items=[to_patient(r) for r in rows], total=total, offset=pg.offset, limit=pg.limit
        )

    def search(self, query: str, paging: Paging | None = None) -> Page[Patient]:
        term = f"%{query.strip().lower()}%"
        q = (
            self._q()
            .filter(
                (PatientModel.first_name.ilike(term))
                | (PatientModel.last_name.ilike(term))
                | (PatientModel.code.ilike(term))
            )
            .order_by(PatientModel.last_name, PatientModel.first_name)
        )
        total = q.count()
        pg = paging or Paging()
        rows = q.offset(pg.offset).limit(pg.limit).all()
        return Page(
            items=[to_patient(r) for r in rows], total=total, offset=pg.offset, limit=pg.limit
        )

    def save(self, patient: Patient) -> None:
        row = self._s.get(PatientModel, patient.id.value)
        if row is None:
            row = PatientModel(id=patient.id.value)
            self._s.add(row)
        row.tenant_id = patient.tenant_id.value
        row.code = patient.code
        row.first_name = patient.first_name
        row.last_name = patient.last_name
        row.sex = str(patient.sex)
        row.date_of_birth = patient.date_of_birth
        row.blood_type = str(patient.blood_type) if patient.blood_type else None
        row.insurance = patient.insurance
        if patient.primary_doctor_id:
            row.primary_doctor_id = patient.primary_doctor_id.value
        else:
            row.primary_doctor_id = None
        row.status = str(patient.status)
        row.tags = patient.tags
        row.allergies = patient.allergies
        row.contact = _contact_to_json(patient.contact)
        row.created_at = patient.created_at
        row.updated_at = patient.updated_at
