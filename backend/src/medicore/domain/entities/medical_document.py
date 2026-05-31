"""MedicalDocument aggregate and the lightweight AttachmentRef value object."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import DocumentKind
from medicore.domain.shared.identifiers import (
    DocumentId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)


@dataclass(frozen=True, slots=True)
class AttachmentRef:
    """A reference to a stored document, embedded in consultations / records."""

    document_id: DocumentId
    file_name: str
    kind: DocumentKind


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
