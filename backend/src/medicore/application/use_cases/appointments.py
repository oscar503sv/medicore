"""Appointment use cases, including availability-aware slot resolution and booking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.tenant import Location
from medicore.domain.entities.user import User
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role
from medicore.domain.repositories._support import UserFilter
from medicore.domain.services.slot_resolver import (
    BusyInterval,
    Slot,
    is_available,
    resolve_available_slots,
)
from medicore.domain.shared.errors import SlotUnavailable
from medicore.domain.shared.identifiers import (
    AppointmentId,
    InsurerId,
    LocationId,
    PatientId,
    UserId,
)

_BLOCKING_STATUSES = {
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.IN_PROGRESS,
}


def _busy_intervals(appointments: list[Appointment]) -> list[BusyInterval]:
    return [
        BusyInterval(a.scheduled_start, a.scheduled_end)
        for a in appointments
        if a.status in _BLOCKING_STATUSES
    ]


def _appt_subject(uow: UnitOfWork, appointment: Appointment) -> str:
    """Audit subject for an appointment: "A-2401 · Lucía Álvarez"."""
    patient = uow.patients.get_by_id(appointment.patient_id)
    return subject(appointment.code, patient.full_name if patient else None)


@dataclass(frozen=True, slots=True)
class CreateAppointmentCommand:
    patient_id: PatientId
    doctor_id: UserId
    location_id: LocationId
    type: AppointmentType
    scheduled_start: datetime
    reason: str
    room: str | None = None
    insurance_id: InsurerId | None = None


@dataclass(frozen=True, slots=True)
class DoctorOption:
    """A bookable doctor plus the appointment duration their rules impose."""

    user: User
    slot_minutes: int | None  # None → the doctor has no availability configured yet


@dataclass(frozen=True, slots=True)
class BookingOptions:
    """Everything the create-appointment UI needs to populate its selectors."""

    doctors: list[DoctorOption]
    locations: list[Location]


class GetBookingOptions:
    """Doctors + locations available for booking. Accessible to appointment managers
    (admin, doctor, receptionist) — unlike the admin-only user/organization endpoints."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> BookingOptions:
        ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)
        doctors = self._uow.users.list(UserFilter(role="doctor", status="active")).items
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        locations = list(tenant.locations) if tenant else []
        options = []
        for doctor in doctors:
            availability = self._uow.availability.get_by_doctor(doctor.id)
            options.append(
                DoctorOption(
                    user=doctor,
                    slot_minutes=availability.rules.slot_minutes if availability else None,
                )
            )
        return BookingOptions(doctors=options, locations=locations)


def _scope_doctor(actor: ActorContext, doctor_id: UserId | None) -> UserId | None:
    """Doctors only ever see their own appointments; other roles may filter by any doctor."""
    if actor.role == Role.DOCTOR:
        return actor.user_id
    return doctor_id


class ListAppointmentsForDay:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, on: date, doctor_id: UserId | None = None
    ) -> list[Appointment]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        return self._uow.appointments.list_by_day(on, _scope_doctor(actor, doctor_id))


class GetWeeklySchedule:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, week_start: date, doctor_id: UserId | None = None
    ) -> dict[date, list[Appointment]]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        scoped = _scope_doctor(actor, doctor_id)
        return {
            (day := week_start + timedelta(days=offset)): self._uow.appointments.list_by_day(
                day, scoped
            )
            for offset in range(7)
        }


class GetAvailableSlots:
    """Resolve a doctor's bookable slots for a date, subtracting existing appointments."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, doctor_id: UserId, on: date) -> list[Slot]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        availability = self._uow.availability.get_by_doctor(doctor_id)
        if availability is None:
            return []
        busy = _busy_intervals(self._uow.appointments.list_by_day(on, doctor_id))
        return resolve_available_slots(
            availability,
            on,
            busy=busy,
            now=clinic_now(self._uow, actor.tenant_id, self._clock),
        )


class CreateAppointment:
    """Book an appointment, validating it against the doctor's availability and existing
    appointments (within availability, no overlap, honoring booking rules)."""

    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreateAppointmentCommand) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)

        availability = self._uow.availability.get_by_doctor(cmd.doctor_id)
        if availability is None:
            raise SlotUnavailable("doctor has no availability configured")

        # Appointment duration is the doctor's rule, never a caller choice.
        duration = availability.rules.slot_minutes
        end = cmd.scheduled_start + timedelta(minutes=duration)
        busy = _busy_intervals(
            self._uow.appointments.find_overlapping(cmd.doctor_id, cmd.scheduled_start, end)
        )
        if not is_available(
            availability,
            cmd.scheduled_start,
            busy=busy,
            now=clinic_now(self._uow, actor.tenant_id, self._clock),
        ):
            raise SlotUnavailable(
                f"{cmd.scheduled_start.isoformat()} is not bookable for doctor {cmd.doctor_id}"
            )

        appointment = Appointment(
            id=AppointmentId.new(),
            tenant_id=actor.tenant_id,
            code=self._codes.next_appointment_code(),
            patient_id=cmd.patient_id,
            doctor_id=cmd.doctor_id,
            location_id=cmd.location_id,
            type=cmd.type,
            scheduled_start=cmd.scheduled_start,
            duration_minutes=duration,
            reason=cmd.reason,
            created_by_id=actor.user_id,
            room=cmd.room,
            insurance_id=cmd.insurance_id,
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        with self._uow:
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor,
                    self._clock.now(),
                    "appointment.created",
                    "Appointment",
                    str(appointment.id),
                    subject=_appt_subject(self._uow, appointment),
                )
            )
            self._uow.commit()
        return appointment


class RescheduleAppointment:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: ActorContext,
        appointment_id: AppointmentId,
        new_start: datetime,
    ) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)
        appointment = self._require(appointment_id)

        availability = self._uow.availability.get_by_doctor(appointment.doctor_id)
        if availability is None:
            raise SlotUnavailable("doctor has no availability configured")
        # Duration is recomputed from the doctor's current rules, not carried over.
        duration = availability.rules.slot_minutes
        end = new_start + timedelta(minutes=duration)
        # Existing appointments excluding the one being moved.
        overlapping = [
            a
            for a in self._uow.appointments.find_overlapping(appointment.doctor_id, new_start, end)
            if a.id != appointment.id
        ]
        if not is_available(
            availability,
            new_start,
            busy=_busy_intervals(overlapping),
            now=clinic_now(self._uow, actor.tenant_id, self._clock),
        ):
            raise SlotUnavailable("new slot is not bookable")

        with self._uow:
            appointment.reschedule(new_start, duration)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "appointment.rescheduled", "Appointment",
                    str(appointment.id), subject=_appt_subject(self._uow, appointment),
                )
            )
            self._uow.commit()
        return appointment

    def _require(self, appointment_id: AppointmentId) -> Appointment:
        appointment = self._uow.appointments.get_by_id(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        return appointment


class _AppointmentTransition:
    """Shared base for the simple status-change use cases."""

    action = "appointment.changed"

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _apply(self, appointment: Appointment) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def execute(self, actor: ActorContext, appointment_id: AppointmentId) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)
        appointment = self._uow.appointments.get_by_id(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        with self._uow:
            self._apply(appointment)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), self.action, "Appointment", str(appointment.id),
                    subject=_appt_subject(self._uow, appointment),
                )
            )
            self._uow.commit()
        return appointment


class ConfirmAppointment(_AppointmentTransition):
    action = "appointment.confirmed"

    def _apply(self, appointment: Appointment) -> None:
        appointment.confirm()


class CancelAppointment(_AppointmentTransition):
    action = "appointment.cancelled"

    def _apply(self, appointment: Appointment) -> None:
        appointment.cancel()


class MarkNoShow(_AppointmentTransition):
    action = "appointment.no_show"

    def _apply(self, appointment: Appointment) -> None:
        appointment.mark_no_show()
