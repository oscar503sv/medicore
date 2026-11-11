"""FeeScheduleRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.shared.identifiers import UserId


class FeeScheduleRepository(Protocol):
    def get_by_doctor(self, doctor_id: UserId) -> FeeSchedule | None: ...

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, FeeSchedule]:
        """Saved schedules per doctor in one go (doctors without one are omitted)."""
        ...

    def save(self, schedule: FeeSchedule) -> None: ...
