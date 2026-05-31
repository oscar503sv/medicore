"""SQLAlchemy repositories for Consultation, MedicalRecord, Prescription, MedicalDocument."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.repositories._support import RecordFilter
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    DocumentId,
    PatientId,
    RecordId,
    TenantId,
)
from medicore.infrastructure.persistence.mappers._json import (
    attachment_to_dict,
    diagnoses_to_list,
    draft_to_dict,
    snapshot_to_dict,
    soap_to_dict,
    vaccine_to_dict,
    vitals_to_dict,
)
from medicore.infrastructure.persistence.mappers.entities import (
    to_consultation,
    to_medical_document,
    to_medical_record,
    to_prescription,
)
from medicore.infrastructure.persistence.models.consultation import ConsultationModel
from medicore.infrastructure.persistence.models.medical_document import MedicalDocumentModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.prescription import PrescriptionModel


class SqlConsultationRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(ConsultationModel).filter(ConsultationModel.tenant_id == self._tid)

    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None:
        row = self._q().filter(ConsultationModel.id == consultation_id.value).first()
        return to_consultation(row) if row else None

    def get_by_appointment(self, appointment_id: AppointmentId) -> Consultation | None:
        row = self._q().filter(ConsultationModel.appointment_id == appointment_id.value).first()
        return to_consultation(row) if row else None

    def save(self, c: Consultation) -> None:
        row = self._s.get(ConsultationModel, c.id.value)
        if row is None:
            row = ConsultationModel(id=c.id.value)
            self._s.add(row)
        row.tenant_id = c.tenant_id.value
        row.appointment_id = c.appointment_id.value
        row.patient_id = c.patient_id.value
        row.doctor_id = c.doctor_id.value
        row.status = str(c.status)
        row.started_at = c.started_at
        row.ended_at = c.ended_at
        row.vitals = vitals_to_dict(c.vitals)
        row.soap = soap_to_dict(c.soap)
        row.diagnoses = diagnoses_to_list(c.diagnoses)
        row.draft_prescriptions = [draft_to_dict(d) for d in c.draft_prescriptions]
        row.attachments = [attachment_to_dict(a) for a in c.attachments]
        row.last_saved_at = c.last_saved_at


class SqlMedicalRecordRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(MedicalRecordModel).filter(MedicalRecordModel.tenant_id == self._tid)

    def get_by_id(self, record_id: RecordId) -> MedicalRecord | None:
        row = self._q().filter(MedicalRecordModel.id == record_id.value).first()
        return to_medical_record(row) if row else None

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]:
        rows = (
            self._q()
            .filter(MedicalRecordModel.patient_id == patient_id.value)
            .order_by(MedicalRecordModel.encounter_at.desc())
            .all()
        )
        return [to_medical_record(r) for r in rows]

    def list(self, filter: RecordFilter | None = None) -> list[MedicalRecord]:
        q = self._q().order_by(MedicalRecordModel.encounter_at.desc())
        if filter and filter.patient_id:
            from uuid import UUID
            q = q.filter(MedicalRecordModel.patient_id == UUID(filter.patient_id))
        if filter and filter.type:
            q = q.filter(MedicalRecordModel.type == filter.type)
        return [to_medical_record(r) for r in q.all()]

    def save(self, record: MedicalRecord) -> None:
        # Records are immutable once signed; amendments are new rows.
        row = self._s.get(MedicalRecordModel, record.id.value)
        if row is not None:
            return  # never overwrite a stored signed record
        row = MedicalRecordModel(id=record.id.value)
        self._s.add(row)
        row.tenant_id = record.tenant_id.value
        row.code = record.code
        row.patient_id = record.patient_id.value
        row.author_id = record.author_id.value
        row.type = str(record.type)
        row.status = str(record.status)
        row.encounter_at = record.encounter_at
        row.location_name = record.location_name
        row.chief_complaint = record.chief_complaint
        row.soap = soap_to_dict(record.soap)
        row.vitals = vitals_to_dict(record.vitals)
        row.diagnoses = diagnoses_to_list(record.diagnoses)
        row.prescriptions = [snapshot_to_dict(p) for p in record.prescriptions]
        row.vaccines = [vaccine_to_dict(v) for v in record.vaccines]
        row.attachments = [attachment_to_dict(a) for a in record.attachments]
        row.signed_at = record.signed_at
        row.signed_by_id = record.signed_by_id.value
        row.appointment_id = record.appointment_id.value if record.appointment_id else None
        row.consultation_id = record.consultation_id.value if record.consultation_id else None
        row.amends_record_id = record.amends_record_id.value if record.amends_record_id else None


class SqlPrescriptionRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(PrescriptionModel).filter(PrescriptionModel.tenant_id == self._tid)

    def list_by_patient(
        self, patient_id: PatientId, active_only: bool = False
    ) -> list[Prescription]:
        q = (
            self._q()
            .filter(PrescriptionModel.patient_id == patient_id.value)
            .order_by(PrescriptionModel.start_date.desc())
        )
        if active_only:
            q = q.filter(PrescriptionModel.status == str(PrescriptionStatus.ACTIVE))
        return [to_prescription(r) for r in q.all()]

    def save(self, prescription: Prescription) -> None:
        row = self._s.get(PrescriptionModel, prescription.id.value)
        if row is None:
            row = PrescriptionModel(id=prescription.id.value)
            self._s.add(row)
        row.tenant_id = prescription.tenant_id.value
        row.patient_id = prescription.patient_id.value
        row.prescriber_id = prescription.prescriber_id.value
        row.drug = prescription.drug
        row.dose = prescription.dose
        row.schedule = prescription.schedule
        row.start_date = prescription.start_date
        row.end_date = prescription.end_date
        row.duration_days = prescription.duration_days
        row.status = str(prescription.status)
        row.record_id = prescription.record_id.value if prescription.record_id else None
        row.created_at = prescription.created_at


class SqlMedicalDocumentRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return (
            self._s.query(MedicalDocumentModel)
            .filter(MedicalDocumentModel.tenant_id == self._tid)
        )

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalDocument]:
        rows = (
            self._q()
            .filter(MedicalDocumentModel.patient_id == patient_id.value)
            .order_by(MedicalDocumentModel.uploaded_at.desc())
            .all()
        )
        return [to_medical_document(r) for r in rows]

    def save(self, document: MedicalDocument) -> None:
        row = self._s.get(MedicalDocumentModel, document.id.value)
        if row is None:
            row = MedicalDocumentModel(id=document.id.value)
            self._s.add(row)
        row.tenant_id = document.tenant_id.value
        row.patient_id = document.patient_id.value
        row.file_name = document.file_name
        row.kind = str(document.kind)
        row.mime_type = document.mime_type
        row.size_bytes = document.size_bytes
        row.storage_key = document.storage_key
        row.uploaded_by_id = document.uploaded_by_id.value
        row.uploaded_at = document.uploaded_at
        row.record_id = document.record_id.value if document.record_id else None

    def delete(self, document_id: DocumentId) -> None:
        row = (
            self._q().filter(MedicalDocumentModel.id == document_id.value).first()
        )
        if row:
            self._s.delete(row)
