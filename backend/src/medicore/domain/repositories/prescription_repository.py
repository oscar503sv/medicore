"""PrescriptionRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.prescription import Prescription
from medicore.domain.shared.identifiers import PatientId, PrescriptionId


class PrescriptionRepository(Protocol):
    def get_by_id(self, prescription_id: PrescriptionId) -> Prescription | None: ...

    def list_by_patient(
        self, patient_id: PatientId, active_only: bool = False
    ) -> list[Prescription]: ...

    def save(self, prescription: Prescription) -> None: ...
