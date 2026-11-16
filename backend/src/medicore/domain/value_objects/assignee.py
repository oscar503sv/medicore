"""Who attends an appointment: one doctor, or one service agenda (never both, never neither)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from medicore.domain.shared.errors import DomainError
from medicore.domain.shared.identifiers import ServiceAgendaId, UserId


@dataclass(frozen=True, slots=True)
class Assignee:
    doctor_id: UserId | None = None
    agenda_id: ServiceAgendaId | None = None

    def __post_init__(self) -> None:
        if (self.doctor_id is None) == (self.agenda_id is None):
            raise DomainError(
                "an appointment belongs to exactly one doctor or one service agenda",
                code="appointment.assignee_required",
            )

    @classmethod
    def doctor(cls, doctor_id: UserId) -> Assignee:
        return cls(doctor_id=doctor_id)

    @classmethod
    def agenda(cls, agenda_id: ServiceAgendaId) -> Assignee:
        return cls(agenda_id=agenda_id)

    @property
    def is_doctor(self) -> bool:
        return self.doctor_id is not None

    @property
    def owner(self) -> UserId | ServiceAgendaId:
        """The doctor's or the agenda's identifier (the invariant guarantees one is set)."""
        return cast("UserId | ServiceAgendaId", self.doctor_id or self.agenda_id)
