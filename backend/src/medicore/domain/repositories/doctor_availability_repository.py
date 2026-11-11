"""DoctorAvailabilityRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.shared.identifiers import UserId


class DoctorAvailabilityRepository(Protocol):
    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None: ...

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, DoctorAvailability]:
        """Saved availability per doctor in one go (doctors without one are omitted)."""
        ...

    def save(self, availability: DoctorAvailability) -> None: ...
