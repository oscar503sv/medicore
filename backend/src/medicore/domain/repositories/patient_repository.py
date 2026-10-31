"""PatientRepository port."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from medicore.domain.entities.patient import Patient
from medicore.domain.repositories._support import Page, Paging, PatientFilter
from medicore.domain.shared.identifiers import PatientId


class PatientRepository(Protocol):
    def get_by_id(self, patient_id: PatientId) -> Patient | None: ...

    def list(
        self, filter: PatientFilter | None = None, paging: Paging | None = None
    ) -> Page[Patient]: ...

    def search(self, query: str, paging: Paging | None = None) -> Page[Patient]: ...

    def count_created_since(self, since: datetime) -> int:
        """Patients registered at or after ``since`` (a UTC instant)."""
        ...

    def save(self, patient: Patient) -> None: ...
