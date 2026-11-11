"""Dashboard summary: the headline numbers on the home page, computed from real data.

Each metric compares against the same window one week earlier. Scope follows the rest of
the app: a doctor sees their own appointments and agenda, other roles the whole clinic.
A metric the actor has no permission for comes back as ``None`` instead of failing the
whole dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from medicore.application.common.context import ActorContext
from medicore.application.common.permissions import Permission, has_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.enums import AppointmentStatus, Role, UserStatus
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.services.slot_resolver import (
    BusyInterval,
    SlotStatus,
    resolve_available_slots,
)
from medicore.domain.shared.identifiers import UserId

_PENDING = {AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED}
_WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    day: date
    # Appointments on ``day`` (cancelled ones excluded) and the change vs. the same weekday
    # last week, in percent. None when there is no baseline to compare against.
    appointments_today: int | None
    appointments_delta_pct: int | None
    # Still to be attended today (scheduled or confirmed).
    pending_today: int | None
    # All registered patients, and growth over the last 7 days in percent.
    patients_total: int | None
    patients_delta_pct: int | None
    # Share of the agenda's bookable time that is booked today, and the change in
    # percentage points vs. the same weekday last week. None without any configured hours.
    occupancy_pct: int | None
    occupancy_delta_pts: int | None


def _pct_change(current: int, previous: int) -> int | None:
    if previous <= 0:
        return None
    return round((current - previous) * 100 / previous)


class GetDashboardSummary:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> DashboardSummary:
        with self._uow:
            today = clinic_now(self._uow, actor.tenant_id, self._clock).date()
            last_week = today - _WEEK
            doctor = actor.user_id if actor.role == Role.DOCTOR else None

            appts_today = appts_delta = pending = None
            occupancy = occupancy_delta = None
            if has_permission(actor, Permission.APPOINTMENTS_VIEW):
                current = self._booked(today, doctor)
                previous = self._booked(last_week, doctor)
                appts_today = len(current)
                appts_delta = _pct_change(len(current), len(previous))
                pending = sum(1 for a in current if a.status in _PENDING)
                # Doctors and their schedules are read once, for both days.
                schedules = self._uow.availability.list_for_doctors(self._doctors_in_scope(doctor))
                occupancy = self._occupancy(today, schedules, current)
                before = self._occupancy(last_week, schedules, previous)
                if occupancy is not None and before is not None:
                    occupancy_delta = occupancy - before

            patients_total = patients_delta = None
            if has_permission(actor, Permission.PATIENTS_VIEW):
                patients_total = self._uow.patients.list(paging=Paging(limit=1)).total
                now = self._clock.now()
                # Patient timestamps are UTC instants; a naive clock (tests) is taken as UTC.
                now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
                new = self._uow.patients.count_created_since(now - _WEEK)
                patients_delta = _pct_change(patients_total, patients_total - new)

        return DashboardSummary(
            day=today,
            appointments_today=appts_today,
            appointments_delta_pct=appts_delta,
            pending_today=pending,
            patients_total=patients_total,
            patients_delta_pct=patients_delta,
            occupancy_pct=occupancy,
            occupancy_delta_pts=occupancy_delta,
        )

    def _booked(self, on: date, doctor: UserId | None) -> list[Appointment]:
        return [
            a
            for a in self._uow.appointments.list_by_day(on, doctor)
            if a.status != AppointmentStatus.CANCELLED
        ]

    def _doctors_in_scope(self, doctor: UserId | None) -> list[UserId]:
        if doctor is not None:
            return [doctor]
        page = self._uow.users.list(
            UserFilter(role=str(Role.DOCTOR), status=str(UserStatus.ACTIVE)),
            Paging(limit=1000),
        )
        return [u.id for u in page.items]

    @staticmethod
    def _occupancy(
        on: date, schedules: dict[UserId, DoctorAvailability], booked: list[Appointment]
    ) -> int | None:
        """Booked share of the bookable slots across the doctors in scope, in percent.

        Every non-cancelled appointment counts as occupying its slot (a no-show still took
        it). Booking rules are ignored: they limit *when* a slot can be booked, not capacity.
        """
        capacity = taken = 0
        start_of_day = datetime.combine(on, time.min)
        for doctor_id, availability in schedules.items():
            busy = [
                BusyInterval(a.scheduled_start, a.scheduled_end)
                for a in booked
                if a.doctor_id == doctor_id
            ]
            for slot in resolve_available_slots(availability, on, busy, now=start_of_day):
                if slot.status == SlotStatus.OUT_OF_HOURS:
                    continue
                capacity += 1
                taken += slot.status == SlotStatus.TAKEN
        if capacity == 0:
            return None
        return round(taken * 100 / capacity)
