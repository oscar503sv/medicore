"""SQLAlchemy repositories for Consultation, MedicalRecord, Prescription, MedicalDocument."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, and_, exists, func, literal_column, or_, select
from sqlalchemy.orm import Session, aliased

from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.repositories._support import Page, Paging, RecordFilter, RecordSummary
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    DocumentId,
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.shared.text import fold
from medicore.infrastructure.persistence.mappers._json import (
    application_draft_to_dict,
    attachment_to_dict,
    diagnoses_to_list,
    draft_to_dict,
    exam_to_dict,
    note_to_dict,
    procedure_draft_to_dict,
    snapshot_to_dict,
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
from medicore.infrastructure.persistence.models.patient import PatientModel, patient_search_sql
from medicore.infrastructure.persistence.models.prescription import PrescriptionModel
from medicore.infrastructure.persistence.models.user import UserModel

_PATIENT_SEARCH_SQL = patient_search_sql("patients.")


class SqlConsultationRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(ConsultationModel).filter(ConsultationModel.tenant_id == self._tid)

    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None:
        row = self._q().filter(ConsultationModel.id == consultation_id.value).first()
        return to_consultation(row) if row else None

    def get_for_update(self, consultation_id: ConsultationId) -> Consultation | None:
        # FOR NO KEY UPDATE: blocks other signs/edits (and plain UPDATEs) of this row; under
        # READ COMMITTED the waiter gets the committed row, so it sees status=signed.
        row = (
            self._q()
            .filter(ConsultationModel.id == consultation_id.value)
            .with_for_update(key_share=True)
            .populate_existing()
            .first()
        )
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
        row.note = note_to_dict(c.note)
        row.diagnoses = diagnoses_to_list(c.diagnoses)
        row.draft_prescriptions = [draft_to_dict(d) for d in c.draft_prescriptions]
        row.draft_applications = [application_draft_to_dict(d) for d in c.draft_applications]
        row.draft_procedures = [procedure_draft_to_dict(d) for d in c.draft_procedures]
        row.draft_exams = [exam_to_dict(e) for e in c.draft_exams]
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

    def get_for_update(self, record_id: RecordId) -> MedicalRecord | None:
        # FOR NO KEY UPDATE: a second amendment waits here and then finds the first one's
        # version; it does not block inserts that merely reference the record.
        row = (
            self._q()
            .filter(MedicalRecordModel.id == record_id.value)
            .with_for_update(key_share=True)
            .populate_existing()
            .first()
        )
        return to_medical_record(row) if row else None

    def successor_id(self, record_id: RecordId) -> RecordId | None:
        found = (
            self._q()
            .with_entities(MedicalRecordModel.id)
            .filter(MedicalRecordModel.amends_record_id == record_id.value)
            .first()
        )
        return RecordId(found[0]) if found else None

    def versions(self, record_id: RecordId) -> list[MedicalRecord]:
        m = MedicalRecordModel
        # Up to the root, then down along the amendments; ``depth`` orders the chain.
        up = (
            select(m.id, m.amends_record_id)
            .where(m.id == record_id.value, m.tenant_id == self._tid)
            .cte("up", recursive=True)
        )
        parent = aliased(m)
        up = up.union_all(
            select(parent.id, parent.amends_record_id).where(
                parent.id == up.c.amends_record_id, parent.tenant_id == self._tid
            )
        )
        root = select(m.id).where(m.id.in_(select(up.c.id)), m.amends_record_id.is_(None))
        down = (
            select(m.id.label("id"), literal_column("0").label("depth"))
            .where(m.id.in_(root), m.tenant_id == self._tid)
            .cte("down", recursive=True)
        )
        child = aliased(m)
        down = down.union_all(
            select(child.id, down.c.depth + 1).where(
                child.amends_record_id == down.c.id, child.tenant_id == self._tid
            )
        )
        rows = (
            self._q()
            .join(down, down.c.id == m.id)
            .order_by(down.c.depth)
            .all()
        )
        return [to_medical_record(r) for r in rows]

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]:
        newer = aliased(MedicalRecordModel)
        rows = (
            self._q()
            .filter(
                MedicalRecordModel.patient_id == patient_id.value,
                ~exists().where(newer.amends_record_id == MedicalRecordModel.id),
            )
            .order_by(MedicalRecordModel.encounter_at.desc())
            .all()
        )
        return [to_medical_record(r) for r in rows]

    def summaries(self, filter: RecordFilter, paging: Paging) -> Page[RecordSummary]:
        m = MedicalRecordModel
        newer = aliased(m)
        q = (
            self._s.query(
                m.id, m.code, m.patient_id, m.type, m.status, m.encounter_at, m.location_name,
                m.signed_by_id, m.consultation_id, m.amends_record_id,
                PatientModel.first_name, PatientModel.last_name, UserModel.name,
            )
            .outerjoin(
                PatientModel,
                and_(PatientModel.id == m.patient_id, PatientModel.tenant_id == self._tid),
            )
            .outerjoin(
                UserModel, and_(UserModel.id == m.signed_by_id, UserModel.tenant_id == self._tid)
            )
            .filter(m.tenant_id == self._tid)
            .filter(~exists().where(newer.amends_record_id == m.id))
        )
        if filter.patient_id:
            q = q.filter(m.patient_id == UUID(filter.patient_id))
        if filter.type:
            q = q.filter(m.type == filter.type)
        if filter.encounter_from:
            q = q.filter(m.encounter_at >= filter.encounter_from)
        if filter.encounter_before:
            q = q.filter(m.encounter_at < filter.encounter_before)
        if filter.search:
            # Literal SQL identical to the patients trigram indexes, so they can be used.
            name = literal_column(_PATIENT_SEARCH_SQL["name"], String)
            patient_code = literal_column(_PATIENT_SEARCH_SQL["code"], String)
            for word in fold(filter.search).split():
                # autoescape neutralizes LIKE wildcards typed into the search box.
                q = q.filter(
                    or_(
                        name.contains(word, autoescape=True),
                        patient_code.contains(word, autoescape=True),
                        func.lower(m.code).contains(word, autoescape=True),
                    )
                )
        total = q.count()
        rows = (
            q.order_by(m.encounter_at.desc(), m.id.desc())
            .offset(paging.offset)
            .limit(paging.limit)
            .all()
        )
        items = [
            RecordSummary(
                id=str(r.id),
                code=r.code,
                patient_id=str(r.patient_id),
                patient_name=f"{r.first_name} {r.last_name}" if r.first_name else None,
                type=r.type,
                status=r.status,
                encounter_at=r.encounter_at,
                location_name=r.location_name,
                signed_by_id=str(r.signed_by_id),
                signed_by_name=r.name,
                consultation_id=str(r.consultation_id) if r.consultation_id else None,
                amends_record_id=str(r.amends_record_id) if r.amends_record_id else None,
            )
            for r in rows
        ]
        return Page(items=items, total=total, offset=paging.offset, limit=paging.limit)

    def exists_by_author(self, author_id: UserId) -> bool:
        return (
            self._q().filter(MedicalRecordModel.author_id == author_id.value).first()
            is not None
        )

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
        row.insurer_name = record.insurer_name
        row.chief_complaint = record.chief_complaint
        row.note = note_to_dict(record.note)
        row.vitals = vitals_to_dict(record.vitals)
        row.diagnoses = diagnoses_to_list(record.diagnoses)
        row.prescriptions = [snapshot_to_dict(p) for p in record.prescriptions]
        row.vaccines = [vaccine_to_dict(v) for v in record.vaccines]
        row.exams = [exam_to_dict(e) for e in record.exams]
        row.attachments = [attachment_to_dict(a) for a in record.attachments]
        row.signed_at = record.signed_at
        row.signed_by_id = record.signed_by_id.value
        row.appointment_id = record.appointment_id.value if record.appointment_id else None
        row.consultation_id = record.consultation_id.value if record.consultation_id else None
        row.amends_record_id = record.amends_record_id.value if record.amends_record_id else None
        row.amendment_reason = record.amendment_reason


class SqlPrescriptionRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(PrescriptionModel).filter(PrescriptionModel.tenant_id == self._tid)

    def get_by_id(self, prescription_id: PrescriptionId) -> Prescription | None:
        row = self._q().filter(PrescriptionModel.id == prescription_id.value).first()
        return to_prescription(row) if row else None

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
