"""MedicalRecordRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.repositories._support import RecordFilter
from medicore.domain.shared.identifiers import PatientId, RecordId


class MedicalRecordRepository(Protocol):
    def get_by_id(self, record_id: RecordId) -> MedicalRecord | None: ...

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]: ...

    def list(self, filter: RecordFilter | None = None) -> list[MedicalRecord]: ...

    def save(self, record: MedicalRecord) -> None:
        """Persist a signed/amended record. Implementations must never overwrite a record
        that is already signed — amendments are saved as new rows."""
        ...
