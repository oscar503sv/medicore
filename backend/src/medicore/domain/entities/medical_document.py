"""MedicalDocument aggregate and the lightweight AttachmentRef value object."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from medicore.domain.enums import DocumentKind
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import (
    DocumentId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)

if TYPE_CHECKING:
    from medicore.domain.entities.medical_record import MedicalRecord


@dataclass(frozen=True, slots=True)
class AttachmentRef:
    """A reference to a stored document, embedded in consultations / records."""

    document_id: DocumentId
    file_name: str
    kind: DocumentKind


def storage_key_for(tenant_id: TenantId, patient_id: PatientId, document_id: DocumentId) -> str:
    """Server-chosen key: the client never names where a file lives."""
    return f"{tenant_id}/{patient_id}/{document_id}"


@dataclass(slots=True)
class MedicalDocument:
    """A medical file (lab/imaging/rx/consent) belonging to a patient.

    Permissions (e.g. nurses may upload) are enforced in the application layer.
    """

    id: DocumentId
    tenant_id: TenantId
    patient_id: PatientId
    file_name: str
    kind: DocumentKind
    mime_type: str
    size_bytes: int
    storage_key: str
    uploaded_by_id: UserId
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    record_id: RecordId | None = None

    def as_ref(self) -> AttachmentRef:
        return AttachmentRef(document_id=self.id, file_name=self.file_name, kind=self.kind)

    @classmethod
    def register(
        cls,
        *,
        tenant_id: TenantId,
        patient_id: PatientId,
        file_name: str,
        kind: DocumentKind,
        mime_type: str,
        size_bytes: int,
        uploaded_by_id: UserId,
        uploaded_at: datetime,
    ) -> MedicalDocument:
        document_id = DocumentId.new()
        return cls(
            id=document_id,
            tenant_id=tenant_id,
            patient_id=patient_id,
            file_name=file_name,
            kind=kind,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_key=storage_key_for(tenant_id, patient_id, document_id),
            uploaded_by_id=uploaded_by_id,
            uploaded_at=uploaded_at,
        )

    def link_to(self, record: MedicalRecord) -> None:
        if record.patient_id != self.patient_id:
            raise InvalidValueObject(
                "the record belongs to another patient", code="document.record_mismatch"
            )
        self.record_id = record.id
