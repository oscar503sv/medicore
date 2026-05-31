"""MedicalDocumentRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.shared.identifiers import DocumentId, PatientId


class MedicalDocumentRepository(Protocol):
    def list_by_patient(self, patient_id: PatientId) -> list[MedicalDocument]: ...

    def save(self, document: MedicalDocument) -> None: ...

    def delete(self, document_id: DocumentId) -> None: ...
