"""AppointmentRepository port."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from medicore.domain.entities.appointment import Appointment
from medicore.domain.shared.identifiers import AppointmentId, PatientId, UserId


class AppointmentRepository(Protocol):
    def get_by_id(self, appointment_id: AppointmentId) -> Appointment | None: ...

    def list_by_day(self, on: date, doctor_id: UserId | None = None) -> list[Appointment]: ...

    def list_by_patient(self, patient_id: PatientId) -> list[Appointment]: ...

    def find_overlapping(
        self, doctor_id: UserId, start: datetime, end: datetime
    ) -> list[Appointment]:
        """Appointments for the doctor intersecting ``[start, end)`` (for slot checks)."""
        ...

    def save(self, appointment: Appointment) -> None: ...
