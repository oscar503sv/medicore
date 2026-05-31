"""DoctorAvailabilityRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.shared.identifiers import UserId


class DoctorAvailabilityRepository(Protocol):
    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None: ...

    def save(self, availability: DoctorAvailability) -> None: ...
