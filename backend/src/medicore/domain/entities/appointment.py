"""Appointment aggregate with an explicit state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.errors import InvalidStateTransition
from medicore.domain.shared.identifiers import (
    AppointmentId,
    LocationId,
    PatientId,
    TenantId,
    UserId,
)

# Allowed transitions of the appointment lifecycle.
#   scheduled → confirmed → in_progress → completed
#   scheduled | confirmed → cancelled | no_show
_TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    AppointmentStatus.SCHEDULED: frozenset(
        {
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.IN_PROGRESS,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.NO_SHOW,
        }
    ),
    AppointmentStatus.CONFIRMED: frozenset(
        {
            AppointmentStatus.IN_PROGRESS,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.NO_SHOW,
        }
    ),
    AppointmentStatus.IN_PROGRESS: frozenset({AppointmentStatus.COMPLETED}),
    AppointmentStatus.COMPLETED: frozenset(),
    AppointmentStatus.CANCELLED: frozenset(),
    AppointmentStatus.NO_SHOW: frozenset(),
}


@dataclass(slots=True)
class Appointment:
    """A scheduled encounter between a patient and a doctor at a location.

    Slot validity (within doctor availability, no overlap, booking rules) is enforced when
    the appointment is created/rescheduled by the application layer via the slot resolver —
    not in this constructor, which has no knowledge of other appointments.
    """

    id: AppointmentId
    tenant_id: TenantId
    code: str  # human-readable, e.g. "A-2401"
    patient_id: PatientId
    doctor_id: UserId
    location_id: LocationId
    type: AppointmentType
    scheduled_start: datetime
    duration_minutes: int
    reason: str
    created_by_id: UserId
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    room: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def scheduled_end(self) -> datetime:
        return self.scheduled_start + timedelta(minutes=self.duration_minutes)

    @property
    def is_active(self) -> bool:
        """True while the appointment can still lead to a consultation."""
        return self.status in {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.IN_PROGRESS,
        }

    # ── state machine ──
    def confirm(self) -> None:
        self._transition_to(AppointmentStatus.CONFIRMED)

    def start(self) -> None:
        """Begin the consultation."""
        self._transition_to(AppointmentStatus.IN_PROGRESS)

    def complete(self) -> None:
        self._transition_to(AppointmentStatus.COMPLETED)

    def cancel(self) -> None:
        self._transition_to(AppointmentStatus.CANCELLED)

    def mark_no_show(self) -> None:
        self._transition_to(AppointmentStatus.NO_SHOW)

    def reschedule(self, new_start: datetime, new_duration: int | None = None) -> None:
        """Move the appointment. Only valid before it starts.

        Slot re-validation is the application layer's responsibility.
        """
        if self.status not in {AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED}:
            raise InvalidStateTransition("Appointment.reschedule", self.status, "reschedule")
        self.scheduled_start = new_start
        if new_duration is not None:
            self.duration_minutes = new_duration
        self._touch()

    def can_transition_to(self, target: AppointmentStatus) -> bool:
        return target in _TRANSITIONS[self.status]

    def _transition_to(self, target: AppointmentStatus) -> None:
        if not self.can_transition_to(target):
            raise InvalidStateTransition("Appointment", self.status, target)
        self.status = target
        self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)
