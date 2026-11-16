"""Appointment aggregate with an explicit state machine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.errors import DomainError, InvalidStateTransition
from medicore.domain.shared.identifiers import (
    AppointmentId,
    InsurerId,
    LocationId,
    PatientId,
    ServiceAgendaId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.assignee import Assignee
from medicore.domain.value_objects.fee import Charge
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.vitals import Vitals

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
    """A scheduled encounter between a patient and a doctor (or a service agenda, such as the
    vaccination room) at a location.

    Slot validity (within doctor availability, no overlap, booking rules) is enforced when
    the appointment is created/rescheduled by the application layer via the slot resolver —
    not in this constructor, which has no knowledge of other appointments.
    """

    id: AppointmentId
    tenant_id: TenantId
    code: str  # human-readable, e.g. "A-2401"
    patient_id: PatientId
    doctor_id: UserId | None  # None when a service agenda attends it
    location_id: LocationId
    type: AppointmentType
    scheduled_start: datetime
    duration_minutes: int
    reason: str
    created_by_id: UserId
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    agenda_id: ServiceAgendaId | None = None
    room: str | None = None
    # Set when the consultation is booked "with insurance"; None means private/out-of-pocket.
    insurance_id: InsurerId | None = None
    # The doctor's fee for this type when it was booked, and what the visit is charged.
    charge: Charge = field(default_factory=Charge)
    # Registered on the spot, without a booked slot (emergencies, patients who just arrived).
    is_walk_in: bool = False
    # Vitals nursing took while the patient waited, before the consultation exists. They move
    # into the consultation when it starts; they never leave the appointment any other way.
    pre_vitals: Vitals = field(default_factory=Vitals)
    pre_vitals_saved_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        Assignee(self.doctor_id, self.agenda_id)  # raises unless exactly one is set

    @property
    def assignee(self) -> Assignee:
        return Assignee(self.doctor_id, self.agenda_id)

    @classmethod
    def walk_in(
        cls,
        *,
        id: AppointmentId,
        tenant_id: TenantId,
        code: str,
        patient_id: PatientId,
        doctor_id: UserId | None,
        location_id: LocationId,
        type: AppointmentType,
        reason: str,
        duration_minutes: int,
        created_by_id: UserId,
        now: datetime,
        agenda_id: ServiceAgendaId | None = None,
        insurance_id: InsurerId | None = None,
        charge: Charge | None = None,
    ) -> Appointment:
        """A patient seen right now: it starts at ``now`` and waits, confirmed, for the doctor."""
        return cls(
            id=id,
            tenant_id=tenant_id,
            code=code,
            patient_id=patient_id,
            doctor_id=doctor_id,
            agenda_id=agenda_id,
            location_id=location_id,
            type=type,
            scheduled_start=now.replace(second=0, microsecond=0),
            duration_minutes=duration_minutes,
            reason=reason,
            created_by_id=created_by_id,
            status=AppointmentStatus.CONFIRMED,
            insurance_id=insurance_id,
            charge=charge or Charge(),
            is_walk_in=True,
        )

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
        self._discard_pre_vitals()

    def mark_no_show(self) -> None:
        if self.is_walk_in:
            # The patient is already in the clinic: there is nobody to miss the visit.
            raise DomainError(
                "a walk-in cannot be a no-show", code="appointment.walk_in_no_show"
            )
        self._transition_to(AppointmentStatus.NO_SHOW)
        self._discard_pre_vitals()

    def reschedule(self, new_start: datetime, new_duration: int | None = None) -> None:
        """Move the appointment. Only valid before it starts.

        Slot re-validation is the application layer's responsibility.
        """
        if self.is_walk_in:
            raise DomainError(
                "a walk-in cannot be rescheduled", code="appointment.walk_in_reschedule"
            )
        if self.status not in {AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED}:
            raise InvalidStateTransition("Appointment.reschedule", self.status, "reschedule")
        self.scheduled_start = new_start
        if new_duration is not None:
            self.duration_minutes = new_duration
        # Readings belong to the visit the patient waited for, not to the new day.
        self._discard_pre_vitals()
        self._touch()

    def record_pre_vitals(
        self, changes: Mapping[str, object], when: datetime | None = None
    ) -> tuple[str, ...]:
        """Merge only the given vital fields taken before the consultation starts. Returns the
        fields that changed. Only a confirmed appointment takes them: once it is in progress
        the consultation holds the vitals. A service agenda's appointment never has a
        consultation, so it takes none."""
        if not self.takes_pre_vitals:
            raise DomainError(
                "vitals can only be taken before the consultation, on a confirmed appointment",
                code="appointment.vitals_closed",
            )
        merged = self.pre_vitals.with_changes(changes)
        changed = self.pre_vitals.changed_fields(merged)
        if changed:
            self.pre_vitals = merged
            self.pre_vitals_saved_at = when or datetime.now(UTC)
            self._touch()
        return changed

    @property
    def takes_pre_vitals(self) -> bool:
        return self.status == AppointmentStatus.CONFIRMED and self.agenda_id is None

    def take_pre_vitals(self) -> tuple[Vitals, datetime | None]:
        """Hand the waiting-room vitals over (to the consultation) and clear them here."""
        taken = (self.pre_vitals, self.pre_vitals_saved_at)
        self._discard_pre_vitals()
        return taken

    def _discard_pre_vitals(self) -> None:
        self.pre_vitals = Vitals()
        self.pre_vitals_saved_at = None

    def adjust_fee(self, charged: Money, note: str | None) -> None:
        """Charge a different amount (a discount, a courtesy, or a price set after booking).
        A cancelled appointment is not charged at all."""
        if self.status == AppointmentStatus.CANCELLED:
            raise DomainError("a cancelled appointment has no fee",
                              code="fee.appointment_cancelled")
        self.charge = self.charge.adjust(charged, note)
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
