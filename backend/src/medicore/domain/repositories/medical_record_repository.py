"""MedicalRecordRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.repositories._support import Page, Paging, RecordFilter, RecordSummary
from medicore.domain.shared.identifiers import PatientId, RecordId, UserId


class MedicalRecordRepository(Protocol):
    def get_by_id(self, record_id: RecordId) -> MedicalRecord | None: ...

    def get_for_update(self, record_id: RecordId) -> MedicalRecord | None:
        """The record, locked until the transaction ends: two amendments of it queue here,
        so the second one finds the first one's version."""
        ...

    def successor_id(self, record_id: RecordId) -> RecordId | None:
        """The version that amends this record, if any."""
        ...

    def versions(self, record_id: RecordId) -> list[MedicalRecord]:
        """The whole chain this record belongs to, oldest first: the last one is current.
        Empty when the record does not exist."""
        ...

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]:
        """Current versions only, newest encounter first."""
        ...

    def summaries(self, filter: RecordFilter, paging: Paging) -> Page[RecordSummary]:
        """Current versions only, newest first. Reads only list columns (no note/vitals JSON),
        names joined in."""
        ...

    def exists_by_author(self, author_id: UserId) -> bool:
        """Whether the user has signed at least one record."""
        ...

    def save(self, record: MedicalRecord) -> None:
        """Persist a signed/amended record. Implementations must never overwrite a record
        that is already signed — amendments are saved as new rows."""
        ...
