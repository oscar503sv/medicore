"""VaccinationRecordRepository port."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.shared.identifiers import PatientId, VaccinationRecordId


class VaccinationRecordRepository(Protocol):
    def get_by_id(self, record_id: VaccinationRecordId) -> VaccinationRecord | None: ...

    def list_by_patient(self, patient_id: PatientId) -> list[VaccinationRecord]:
        """Every record of the patient, voided ones included, newest first."""
        ...

    def list_active_by_patients(
        self, patient_ids: list[PatientId]
    ) -> list[VaccinationRecord]:
        """Non-voided records of the given patients (for the vaccination worklist)."""
        ...

    def list_administered_on(self, day: date) -> list[VaccinationRecord]:
        """Non-voided doses given at the clinic on ``day``."""
        ...

    def save(self, record: VaccinationRecord) -> None: ...
