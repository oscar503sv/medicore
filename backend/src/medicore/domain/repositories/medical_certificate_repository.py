"""MedicalCertificateRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.shared.identifiers import CertificateId, PatientId, RecordId


class MedicalCertificateRepository(Protocol):
    def get_by_id(self, certificate_id: CertificateId) -> MedicalCertificate | None: ...

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalCertificate]:
        """Newest first."""
        ...

    def list_by_record(self, record_id: RecordId) -> list[MedicalCertificate]:
        """Newest first."""
        ...

    def save(self, certificate: MedicalCertificate) -> None: ...
