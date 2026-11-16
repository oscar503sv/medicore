"""DoctorAvailabilityRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.shared.identifiers import ServiceAgendaId, UserId
from medicore.domain.value_objects.assignee import Assignee


class DoctorAvailabilityRepository(Protocol):
    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None: ...

    def get_by_agenda(self, agenda_id: ServiceAgendaId) -> DoctorAvailability | None: ...

    def get_by_assignee(self, assignee: Assignee) -> DoctorAvailability | None:
        """The schedule of the doctor or service agenda."""
        ...

    def list_for_agendas(
        self, agenda_ids: list[ServiceAgendaId]
    ) -> dict[ServiceAgendaId, DoctorAvailability]:
        """Saved availability per agenda in one go (agendas without one are omitted)."""
        ...

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, DoctorAvailability]:
        """Saved availability per doctor in one go (doctors without one are omitted)."""
        ...

    def save(self, availability: DoctorAvailability) -> None: ...
