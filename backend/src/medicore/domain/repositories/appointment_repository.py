"""AppointmentRepository port."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from medicore.domain.entities.appointment import Appointment
from medicore.domain.shared.identifiers import (
    AppointmentId,
    PatientId,
    ServiceAgendaId,
    UserId,
)
from medicore.domain.value_objects.assignee import Assignee


class AppointmentRepository(Protocol):
    def get_by_id(self, appointment_id: AppointmentId) -> Appointment | None: ...

    def list_by_day(
        self,
        on: date,
        doctor_id: UserId | None = None,
        agenda_id: ServiceAgendaId | None = None,
    ) -> list[Appointment]:
        """The day's appointments, optionally of one doctor or of one service agenda."""
        ...

    def list_by_patient(self, patient_id: PatientId) -> list[Appointment]: ...

    def next_visits(
        self, patient_ids: list[PatientId], now: datetime
    ) -> dict[PatientId, datetime]:
        """Earliest active appointment after ``now`` per patient (omits those without one)."""
        ...

    def last_visits(self, patient_ids: list[PatientId]) -> dict[PatientId, datetime]:
        """Start of the latest completed appointment per patient (omits those without one)."""
        ...

    def exists_for_doctor(self, doctor_id: UserId) -> bool:
        """Whether the doctor has ever had an appointment booked (any status)."""
        ...

    def count_patients_with_upcoming(self, now: datetime) -> int:
        """Distinct patients with an active appointment after ``now`` (clinic wall-clock)."""
        ...

    def list_upcoming(
        self, after: datetime, limit: int, doctor_id: UserId | None = None
    ) -> list[Appointment]:
        """Scheduled or confirmed appointments starting at/after ``after`` (clinic
        wall-clock), soonest first, at most ``limit``. Walk-ins (which start when they are
        registered) also count while they wait, from the start of ``after``'s day."""
        ...

    def find_overlapping(
        self, assignee: Assignee, start: datetime, end: datetime
    ) -> list[Appointment]:
        """Appointments of the doctor or agenda intersecting ``[start, end)`` (for slot checks)."""
        ...

    def get_for_update(self, appointment_id: AppointmentId) -> Appointment | None:
        """Load the appointment and hold its row until the transaction ends, so concurrent
        starts, cancellations, signatures and fee changes of the same appointment run one
        after another and each sees what the other committed.

        Lock order everywhere, so no two transactions wait on each other:
        1. a clinical document: a consultation or a procedure (never both in one
           transaction);
        2. the appointment;
        3. the assignee's bookings (``lock_bookings``);
        4. a counter (record code, appointment code, ...), always last.
        Never lock a consultation or a procedure while holding an appointment, and never
        lock anything while holding a counter. Plain reads do not lock.
        """
        ...

    def lock_bookings(self, assignee: Assignee) -> None:
        """Serialize, until the transaction ends, everything that books or moves an
        appointment of this doctor or service agenda, so the overlap check that follows sees
        what concurrent bookings committed. Level 3 of the lock order: after the appointment
        being moved, before any counter."""
        ...

    def save(self, appointment: Appointment) -> None: ...
