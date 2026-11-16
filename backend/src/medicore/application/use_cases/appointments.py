"""Appointment use cases, including availability-aware slot resolution and booking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from medicore.application.common.appointment_access import ensure_own_appointment
from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.entitlements import ensure_module
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.notifications import (
    APPOINTMENT_CANCELLED,
    APPOINTMENT_CREATED,
    APPOINTMENT_NO_SHOW,
    APPOINTMENT_RESCHEDULED,
    APPOINTMENT_WALK_IN,
    appointment_payload,
    notify,
)
from medicore.application.common.permissions import Permission, ensure_permission, has_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.application.use_cases.fees import list_price
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import BookingRules
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import (
    AddonModule,
    AppointmentStatus,
    AppointmentType,
    PatientStatus,
    Role,
)
from medicore.domain.repositories._support import UserFilter
from medicore.domain.services.slot_resolver import (
    BusyInterval,
    Slot,
    is_available,
    resolve_available_slots,
)
from medicore.domain.shared.errors import PermissionDenied, SlotUnavailable
from medicore.domain.shared.identifiers import (
    AppointmentId,
    InsurerId,
    LocationId,
    PatientId,
    ServiceAgendaId,
    UserId,
)
from medicore.domain.value_objects.assignee import Assignee
from medicore.domain.value_objects.fee import Charge

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


_TYPE_MODULES = {
    AppointmentType.PROCEDURE: AddonModule.PROCEDURES,
    AppointmentType.VACCINATION: AddonModule.VACCINATION,
}


def _required_module(kind: AppointmentType, agenda: ServiceAgenda | None) -> AddonModule | None:
    """The module a clinic needs to book this: the agenda's own, or the type's."""
    return agenda.module if agenda is not None else _TYPE_MODULES.get(kind)


def _ensure_doctor_attendable(
    uow: UnitOfWork, actor: ActorContext, doctor_id: UserId | None, invalid_code: str
) -> None:
    """A doctor books only for themselves or a service agenda (never another doctor); and
    whoever books must name an active doctor."""
    if doctor_id is None:
        return
    if actor.role == Role.DOCTOR and doctor_id != actor.user_id:
        raise PermissionDenied(
            "doctors may only book appointments for themselves", code="appointment.not_own"
        )
    doctor = uow.users.get_by_id(doctor_id)
    if doctor is None or doctor.role != Role.DOCTOR or not doctor.is_active:
        raise ValidationError("the doctor must be an active doctor", code=invalid_code)


def _ensure_patient(uow: UnitOfWork, patient_id: PatientId, inactive_code: str) -> None:
    patient = uow.patients.get_by_id(patient_id)
    if patient is None:
        raise EntityNotFound("Patient", patient_id)
    if patient.status != PatientStatus.ACTIVE:
        raise ValidationError("the patient is not active", code=inactive_code)


def _ensure_location_and_insurer(
    uow: UnitOfWork,
    tenant: Tenant,
    location_id: LocationId,
    insurance_id: InsurerId | None,
    location_code: str,
    insurer_code: str,
) -> None:
    """The ids a request carries must belong to the clinic, not to another one."""
    if all(loc.id != location_id for loc in tenant.locations):
        raise ValidationError("unknown location", code=location_code)
    if insurance_id is not None and uow.insurers.get_by_id(insurance_id) is None:
        raise ValidationError("unknown insurer", code=insurer_code)


def _bookable_agenda(
    uow: UnitOfWork, assignee: Assignee, kind: AppointmentType
) -> ServiceAgenda | None:
    """The agenda that would attend the appointment (None for a doctor's), checked to be
    active and to take that type of appointment."""
    if assignee.agenda_id is None:
        return None
    agenda = uow.service_agendas.get_by_id(assignee.agenda_id)
    if agenda is None:
        raise EntityNotFound("ServiceAgenda", assignee.agenda_id)
    if not agenda.active:
        raise ValidationError("the service agenda is archived", code="service_agenda.inactive")
    agenda.ensure_accepts(kind)
    return agenda


def _charge_for(uow: UnitOfWork, assignee: Assignee, kind: AppointmentType) -> Charge:
    """The doctor's price for this type right now (later price changes don't touch it). An
    agenda has none: vaccines are priced from a catalog, not per appointment."""
    if assignee.doctor_id is None:
        return Charge()
    return Charge.at_list_price(list_price(uow, assignee.doctor_id, kind))


@dataclass(frozen=True, slots=True)
class CreateAppointmentCommand:
    """Exactly one of ``doctor_id`` and ``agenda_id`` says who attends."""

    patient_id: PatientId
    doctor_id: UserId | None
    location_id: LocationId
    type: AppointmentType
    scheduled_start: datetime
    reason: str
    room: str | None = None
    insurance_id: InsurerId | None = None
    agenda_id: ServiceAgendaId | None = None


@dataclass(frozen=True, slots=True)
class WalkInCommand:
    """A patient seen right now. No time: it always starts at the clinic's current minute."""

    patient_id: PatientId
    doctor_id: UserId | None
    reason: str
    type: AppointmentType = AppointmentType.EMERGENCY
    location_id: LocationId | None = None  # the primary location when omitted
    insurance_id: InsurerId | None = None
    agenda_id: ServiceAgendaId | None = None


@dataclass(frozen=True, slots=True)
class DoctorOption:
    """A bookable doctor plus the appointment duration their rules impose."""

    user: User
    slot_minutes: int | None  # None → the doctor has no availability configured yet


@dataclass(frozen=True, slots=True)
class AgendaOption:
    """A bookable service agenda plus the appointment duration its rules impose."""

    agenda: ServiceAgenda
    slot_minutes: int | None  # None → the agenda has no availability configured yet


@dataclass(frozen=True, slots=True)
class BookingOptions:
    """Everything the create-appointment UI needs to populate its selectors."""

    doctors: list[DoctorOption]
    locations: list[Location]
    agendas: list[AgendaOption]


class GetBookingOptions:
    """Doctors, service agendas + locations available for booking. Accessible to appointment
    managers (admin, doctor, receptionist) — unlike the admin-only user/organization endpoints."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> BookingOptions:
        # Walk-in registration picks a doctor and a location too.
        if not (
            has_permission(actor, Permission.APPOINTMENTS_MANAGE)
            or has_permission(actor, Permission.APPOINTMENTS_WALK_IN)
        ):
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
        agendas = []
        listed = [
            a for a in self._uow.service_agendas.list(active_only=True)
            if tenant is not None and tenant.subscription.has_module(a.module)
        ]
        schedules = self._uow.availability.list_for_agendas([a.id for a in listed])
        for agenda in listed:
            availability = schedules.get(agenda.id)
            agendas.append(
                AgendaOption(
                    agenda=agenda,
                    slot_minutes=availability.rules.slot_minutes if availability else None,
                )
            )
        return BookingOptions(doctors=options, locations=locations, agendas=agendas)


def _scope_doctor(actor: ActorContext, doctor_id: UserId | None) -> UserId | None:
    """Doctors only ever see their own appointments; other roles may filter by any doctor."""
    if actor.role == Role.DOCTOR:
        return actor.user_id
    return doctor_id


class ListAppointmentsForDay:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self,
        actor: ActorContext,
        on: date,
        doctor_id: UserId | None = None,
        agenda_id: ServiceAgendaId | None = None,
    ) -> list[Appointment]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        return self._uow.appointments.list_by_day(on, _scope_doctor(actor, doctor_id), agenda_id)


class ListUpcomingAppointments:
    """The next appointments still to be attended, from now on and across days (dashboard).

    Doctors only see their own agenda, like everywhere else."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, limit: int = 6) -> list[Appointment]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        now = clinic_now(self._uow, actor.tenant_id, self._clock)
        return self._uow.appointments.list_upcoming(now, limit, _scope_doctor(actor, None))


class GetWeeklySchedule:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self,
        actor: ActorContext,
        week_start: date,
        doctor_id: UserId | None = None,
        agenda_id: ServiceAgendaId | None = None,
    ) -> dict[date, list[Appointment]]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        scoped = _scope_doctor(actor, doctor_id)
        return {
            (day := week_start + timedelta(days=offset)): self._uow.appointments.list_by_day(
                day, scoped, agenda_id
            )
            for offset in range(7)
        }


class GetAvailableSlots:
    """Resolve a doctor's or service agenda's bookable slots for a date, subtracting existing
    appointments."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, assignee: Assignee, on: date) -> list[Slot]:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        availability = self._uow.availability.get_by_assignee(assignee)
        if availability is None:
            return []
        busy = _busy_intervals(
            self._uow.appointments.list_by_day(on, assignee.doctor_id, assignee.agenda_id)
        )
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
        assignee = Assignee(cmd.doctor_id, cmd.agenda_id)
        _ensure_doctor_attendable(self._uow, actor, cmd.doctor_id, "appointment.invalid_doctor")
        agenda = _bookable_agenda(self._uow, assignee, cmd.type)
        tenant = ensure_module(
            self._uow, actor, _required_module(cmd.type, agenda), "appointment.module_required"
        )
        _ensure_patient(self._uow, cmd.patient_id, "appointment.patient_inactive")
        _ensure_location_and_insurer(
            self._uow, tenant, cmd.location_id, cmd.insurance_id,
            "appointment.invalid_location", "appointment.invalid_insurer",
        )

        with self._uow:
            # Held until the commit: two bookings of the same slot queue here, and the second
            # one sees the first in the overlap check. Always before the code counter.
            self._uow.appointments.lock_bookings(assignee)

            availability = self._uow.availability.get_by_assignee(assignee)
            if availability is None:
                raise SlotUnavailable(
                    "no availability configured", code="slot.no_availability"
                )

            # Appointment duration is the assignee's rule, never a caller choice.
            duration = availability.rules.slot_minutes
            end = cmd.scheduled_start + timedelta(minutes=duration)
            busy = _busy_intervals(
                self._uow.appointments.find_overlapping(assignee, cmd.scheduled_start, end)
            )
            if not is_available(
                availability,
                cmd.scheduled_start,
                busy=busy,
                now=clinic_now(self._uow, actor.tenant_id, self._clock),
            ):
                raise SlotUnavailable(
                    f"{cmd.scheduled_start.isoformat()} is not bookable for {assignee.owner}",
                    code="slot.not_bookable",
                )

            appointment = Appointment(
                id=AppointmentId.new(),
                tenant_id=actor.tenant_id,
                code=self._codes.next_appointment_code(),
                patient_id=cmd.patient_id,
                doctor_id=cmd.doctor_id,
                agenda_id=cmd.agenda_id,
                location_id=cmd.location_id,
                type=cmd.type,
                scheduled_start=cmd.scheduled_start,
                duration_minutes=duration,
                reason=cmd.reason,
                created_by_id=actor.user_id,
                room=cmd.room,
                insurance_id=cmd.insurance_id,
                charge=_charge_for(self._uow, assignee, cmd.type),
                created_at=self._clock.now(),
                updated_at=self._clock.now(),
            )
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
            # An agenda has no doctor to tell: the notification skips a missing recipient.
            notify(
                self._uow, actor, self._clock.now(), APPOINTMENT_CREATED,
                [appointment.doctor_id], **appointment_payload(self._uow, appointment),
            )
            self._uow.commit()
        return appointment


class RegisterWalkIn:
    """Register a patient who is already in the clinic, without looking for a slot.

    Allowed outside the doctor's hours and over other appointments on purpose: an emergency
    does not wait for a free slot. The appointment starts now, confirmed, and the doctor
    starts the consultation with the usual flow."""

    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: WalkInCommand) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_WALK_IN)

        _ensure_patient(self._uow, cmd.patient_id, "walk_in.patient_inactive")
        assignee = Assignee(cmd.doctor_id, cmd.agenda_id)
        _ensure_doctor_attendable(self._uow, actor, cmd.doctor_id, "walk_in.invalid_doctor")
        agenda = _bookable_agenda(self._uow, assignee, cmd.type)
        tenant = ensure_module(
            self._uow, actor, _required_module(cmd.type, agenda), "walk_in.module_required"
        )
        location_id = cmd.location_id or tenant.primary_location.id
        _ensure_location_and_insurer(
            self._uow, tenant, location_id, cmd.insurance_id,
            "walk_in.invalid_location", "walk_in.invalid_insurer",
        )

        availability = self._uow.availability.get_by_assignee(assignee)
        duration = (availability.rules if availability else BookingRules()).slot_minutes
        now = clinic_now(self._uow, actor.tenant_id, self._clock).replace(second=0, microsecond=0)

        with self._uow:
            # The assignee's bookings first, so a walk-in and a booking of the same doctor or
            # agenda see each other; then the counter, which serializes this tenant's creations
            # so two simultaneous registrations of the same patient see each other below.
            self._uow.appointments.lock_bookings(assignee)
            code = self._codes.next_appointment_code()
            end = now + timedelta(minutes=duration)
            same_patient = [
                a
                for a in self._uow.appointments.find_overlapping(assignee, now, end)
                if a.patient_id == cmd.patient_id
            ]
            if same_patient:
                raise SlotUnavailable(
                    "the patient already has an active appointment here now",
                    code="walk_in.duplicate", appointment_code=same_patient[0].code,
                )
            appointment = Appointment.walk_in(
                id=AppointmentId.new(),
                tenant_id=actor.tenant_id,
                code=code,
                patient_id=cmd.patient_id,
                doctor_id=cmd.doctor_id,
                agenda_id=cmd.agenda_id,
                location_id=location_id,
                type=cmd.type,
                reason=cmd.reason,
                duration_minutes=duration,
                created_by_id=actor.user_id,
                now=now,
                insurance_id=cmd.insurance_id,
                charge=_charge_for(self._uow, assignee, cmd.type),
            )
            appointment.created_at = appointment.updated_at = self._clock.now()
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "appointment.walk_in", "Appointment",
                    str(appointment.id), subject=_appt_subject(self._uow, appointment),
                )
            )
            notify(
                self._uow, actor, self._clock.now(), APPOINTMENT_WALK_IN,
                [appointment.doctor_id], **appointment_payload(self._uow, appointment),
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
        with self._uow:
            appointment = self._require(appointment_id)
            # After the appointment, before the overlap check: serializes against bookings
            # and other moves of this assignee. The assignee never changes on a reschedule.
            ensure_own_appointment(actor, appointment)
            assignee = appointment.assignee
            self._uow.appointments.lock_bookings(assignee)

            availability = self._uow.availability.get_by_assignee(assignee)
            if availability is None:
                raise SlotUnavailable(
                    "no availability configured", code="slot.no_availability"
                )
            # Duration is recomputed from the assignee's current rules, not carried over.
            duration = availability.rules.slot_minutes
            end = new_start + timedelta(minutes=duration)
            # Existing appointments excluding the one being moved.
            overlapping = [
                a
                for a in self._uow.appointments.find_overlapping(assignee, new_start, end)
                if a.id != appointment.id
            ]
            if not is_available(
                availability,
                new_start,
                busy=_busy_intervals(overlapping),
                now=clinic_now(self._uow, actor.tenant_id, self._clock),
            ):
                raise SlotUnavailable("new slot is not bookable", code="slot.not_bookable")

            previous_start = appointment.scheduled_start
            appointment.reschedule(new_start, duration)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "appointment.rescheduled", "Appointment",
                    str(appointment.id), subject=_appt_subject(self._uow, appointment),
                )
            )
            notify(
                self._uow, actor, self._clock.now(), APPOINTMENT_RESCHEDULED,
                [appointment.doctor_id], **appointment_payload(self._uow, appointment),
                previous_start=previous_start.isoformat(),
            )
            self._uow.commit()
        return appointment

    def _require(self, appointment_id: AppointmentId) -> Appointment:
        # Locked inside the unit of work: it is held until the commit or rollback, and a
        # status change that won the race is seen here.
        appointment = self._uow.appointments.get_for_update(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        return appointment


class _AppointmentTransition:
    """Shared base for the simple status-change use cases."""

    action = "appointment.changed"
    # Notification sent to the appointment's doctor, or None for transitions not worth one.
    notification: str | None = None

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _apply(self, appointment: Appointment) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def execute(self, actor: ActorContext, appointment_id: AppointmentId) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)
        with self._uow:
            # Locked before deciding: a consultation signed or started meanwhile is seen.
            appointment = self._uow.appointments.get_for_update(appointment_id)
            if appointment is None:
                raise EntityNotFound("Appointment", appointment_id)
            ensure_own_appointment(actor, appointment)
            self._apply(appointment)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), self.action, "Appointment", str(appointment.id),
                    subject=_appt_subject(self._uow, appointment),
                )
            )
            if self.notification is not None:
                notify(
                    self._uow, actor, self._clock.now(), self.notification,
                    [appointment.doctor_id], **appointment_payload(self._uow, appointment),
                )
            self._uow.commit()
        return appointment


class ConfirmAppointment(_AppointmentTransition):
    action = "appointment.confirmed"

    def _apply(self, appointment: Appointment) -> None:
        appointment.confirm()


class CancelAppointment(_AppointmentTransition):
    action = "appointment.cancelled"
    notification = APPOINTMENT_CANCELLED

    def _apply(self, appointment: Appointment) -> None:
        appointment.cancel()


class MarkNoShow(_AppointmentTransition):
    action = "appointment.no_show"
    notification = APPOINTMENT_NO_SHOW

    def _apply(self, appointment: Appointment) -> None:
        appointment.mark_no_show()
