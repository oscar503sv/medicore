"""Medical record and document use cases."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import DocumentKind
from medicore.domain.repositories._support import RecordFilter
from medicore.domain.shared.identifiers import (
    DocumentId,
    PatientId,
    RecordId,
)


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    patient_id: PatientId
    file_name: str
    kind: DocumentKind
    mime_type: str
    size_bytes: int
    storage_key: str
    record_id: RecordId | None = None


class ListMedicalRecords:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, filter: RecordFilter | None = None
    ) -> list[MedicalRecord]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        return self._uow.medical_records.list(filter)


class GetMedicalRecord:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, record_id: RecordId) -> MedicalRecord:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        record = self._uow.medical_records.get_by_id(record_id)
        if record is None:
            raise EntityNotFound("MedicalRecord", record_id)
        # Accessing patient clinical data is auditable (HIPAA/GDPR).
        patient = self._uow.patients.get_by_id(record.patient_id)
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.viewed", "MedicalRecord", str(record_id),
                    subject=subject(record.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return record


class AmendMedicalRecord:
    """Create a versioned amendment that references the original; never mutates it."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, record_id: RecordId, **changes: object
    ) -> MedicalRecord:
        ensure_permission(actor, Permission.RECORDS_AMEND)
        original = self._uow.medical_records.get_by_id(record_id)
        if original is None:
            raise EntityNotFound("MedicalRecord", record_id)
        patient = self._uow.patients.get_by_id(original.patient_id)

        with self._uow:
            amendment = original.amend(
                new_id=RecordId.new(),
                author_id=actor.user_id,
                signed_at=self._clock.now(),
                **changes,
            )
            self._uow.medical_records.save(amendment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.amended", "MedicalRecord",
                    str(amendment.id), amends=str(original.id),
                    subject=subject(amendment.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return amendment


class UploadDocument:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: UploadDocumentCommand) -> MedicalDocument:
        ensure_permission(actor, Permission.RECORDS_UPLOAD)
        document = MedicalDocument(
            id=DocumentId.new(),
            tenant_id=actor.tenant_id,
            patient_id=cmd.patient_id,
            file_name=cmd.file_name,
            kind=cmd.kind,
            mime_type=cmd.mime_type,
            size_bytes=cmd.size_bytes,
            storage_key=cmd.storage_key,
            uploaded_by_id=actor.user_id,
            uploaded_at=self._clock.now(),
            record_id=cmd.record_id,
        )
        with self._uow:
            self._uow.documents.save(document)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "document.uploaded", "MedicalDocument",
                    str(document.id), subject=subject(document.file_name),
                )
            )
            self._uow.commit()
        return document


class ListPatientDocuments:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[MedicalDocument]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        return self._uow.documents.list_by_patient(patient_id)
