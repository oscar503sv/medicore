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

    def next_visits(
        self, patient_ids: list[PatientId], now: datetime
    ) -> dict[PatientId, datetime]:
        """Earliest active appointment after ``now`` per patient (omits those without one)."""
        ...

    def last_visits(self, patient_ids: list[PatientId]) -> dict[PatientId, datetime]:
        """Start of the latest completed appointment per patient (omits those without one)."""
        ...

    def count_patients_with_upcoming(self, now: datetime) -> int:
        """Distinct patients with an active appointment after ``now`` (clinic wall-clock)."""
        ...

    def list_upcoming(
        self, after: datetime, limit: int, doctor_id: UserId | None = None
    ) -> list[Appointment]:
        """Scheduled or confirmed appointments starting at/after ``after`` (clinic
        wall-clock), soonest first, at most ``limit``."""
        ...

    def find_overlapping(
        self, doctor_id: UserId, start: datetime, end: datetime
    ) -> list[Appointment]:
        """Appointments for the doctor intersecting ``[start, end)`` (for slot checks)."""
        ...

    def save(self, appointment: Appointment) -> None: ...
