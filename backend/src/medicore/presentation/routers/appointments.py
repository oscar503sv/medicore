"""Appointments router."""

from __future__ import annotations

from datetime import date
from typing import cast

from fastapi import APIRouter, Query

from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    GetAvailableSlots,
    GetBookingOptions,
    GetWeeklySchedule,
    ListAppointmentsForDay,
    ListUpcomingAppointments,
    MarkNoShow,
    RegisterWalkIn,
    RescheduleAppointment,
    WalkInCommand,
)
from medicore.application.use_cases.consultations import (
    GetAppointmentVitals,
    UpdateAppointmentVitals,
)
from medicore.application.use_cases.fees import AdjustAppointmentFee
from medicore.domain.shared.identifiers import (
    AppointmentId,
    InsurerId,
    LocationId,
    PatientId,
    ServiceAgendaId,
    UserId,
)
from medicore.domain.value_objects.assignee import Assignee
from medicore.domain.value_objects.fee import fee
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.appointments import (
    AppointmentResponse,
    BookingOptionsResponse,
    CreateAppointmentRequest,
    RescheduleRequest,
    SlotResponse,
    WalkInRequest,
    WeeklyScheduleResponse,
)
from medicore.presentation.schemas.consultations import (
    AppointmentVitalsResponse,
    VitalsUpdateRequest,
    vital_changes,
)
from medicore.presentation.schemas.fees import ChargeRequest
from medicore.presentation.serializers import (
    ser_appointment,
    ser_appointment_vitals,
    ser_appointments,
    ser_slot,
    ser_user,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/booking-options", response_model=BookingOptionsResponse)
def booking_options(actor: Actor, uow: UoW):
    with uow:
        opts = GetBookingOptions(uow).execute(actor)
    return BookingOptionsResponse(
        doctors=[{**ser_user(d.user), "slot_minutes": d.slot_minutes} for d in opts.doctors],
        locations=[
            {
                "id": str(loc.id),
                "name": loc.name,
                "address": loc.address,
                "is_primary": loc.is_primary,
            }
            for loc in opts.locations
        ],
        agendas=[
            {
                "id": str(o.agenda.id),
                "name": o.agenda.name,
                "kind": str(o.agenda.kind),
                "location_id": str(o.agenda.location_id) if o.agenda.location_id else None,
                "slot_minutes": o.slot_minutes,
            }
            for o in opts.agendas
        ],
    )


def _optional_id[T: (UserId, ServiceAgendaId)](raw: str | None, id_type: type[T]) -> T | None:
    return cast(T, id_type.parse(raw)) if raw else None


@router.get("", response_model=list[AppointmentResponse])
def list_for_day(
    actor: Actor,
    uow: UoW,
    on: date = Query(...),
    doctor_id: str | None = Query(None),
    agenda_id: str | None = Query(None),
):
    with uow:
        appts = ListAppointmentsForDay(uow).execute(
            actor, on, _optional_id(doctor_id, UserId), _optional_id(agenda_id, ServiceAgendaId)
        )
        return ser_appointments(uow, appts)


@router.get("/upcoming", response_model=list[AppointmentResponse])
def list_upcoming(actor: Actor, uow: UoW, clock: Clock, limit: int = Query(6, ge=1, le=50)):
    """Next scheduled/confirmed appointments from now on, across days (dashboard)."""
    with uow:
        appts = ListUpcomingAppointments(uow, clock).execute(actor, limit)
        return ser_appointments(uow, appts)


@router.get("/schedule", response_model=WeeklyScheduleResponse)
def weekly_schedule(
    actor: Actor,
    uow: UoW,
    week_start: date = Query(...),
    doctor_id: str | None = Query(None),
    agenda_id: str | None = Query(None),
):
    with uow:
        schedule = GetWeeklySchedule(uow).execute(
            actor, week_start, _optional_id(doctor_id, UserId),
            _optional_id(agenda_id, ServiceAgendaId),
        )
        return WeeklyScheduleResponse(
            schedule={
                d.isoformat(): ser_appointments(uow, appts) for d, appts in schedule.items()
            }
        )


@router.get("/slots", response_model=list[SlotResponse])
def available_slots(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    on: date = Query(...),
    doctor_id: str | None = Query(None),
    agenda_id: str | None = Query(None),
):
    # Exactly one of doctor_id and agenda_id (Assignee refuses anything else with a 422).
    assignee = Assignee(
        _optional_id(doctor_id, UserId), _optional_id(agenda_id, ServiceAgendaId)
    )
    with uow:
        slots = GetAvailableSlots(uow, clock).execute(actor, assignee, on)
    return [ser_slot(s) for s in slots]


@router.post("", response_model=AppointmentResponse, status_code=201)
def create_appointment(
    body: CreateAppointmentRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock
):
    cmd = CreateAppointmentCommand(
        patient_id=PatientId.parse(body.patient_id),
        doctor_id=_optional_id(body.doctor_id, UserId),
        agenda_id=_optional_id(body.agenda_id, ServiceAgendaId),
        location_id=LocationId.parse(body.location_id),
        type=body.type,
        scheduled_start=body.scheduled_start,
        reason=body.reason,
        room=body.room,
        insurance_id=InsurerId.parse(body.insurance_id) if body.insurance_id else None,
    )
    appt = CreateAppointment(uow, codes, clock).execute(actor, cmd)
    return ser_appointment(appt)


@router.post("/walk-in", response_model=AppointmentResponse, status_code=201)
def register_walk_in(body: WalkInRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock):
    cmd = WalkInCommand(
        patient_id=PatientId.parse(body.patient_id),
        doctor_id=_optional_id(body.doctor_id, UserId),
        agenda_id=_optional_id(body.agenda_id, ServiceAgendaId),
        location_id=LocationId.parse(body.location_id) if body.location_id else None,
        type=body.type,
        reason=body.reason,
        insurance_id=InsurerId.parse(body.insurance_id) if body.insurance_id else None,
    )
    return ser_appointment(RegisterWalkIn(uow, codes, clock).execute(actor, cmd))


@router.put("/{appointment_id}/reschedule", response_model=AppointmentResponse)
def reschedule(appointment_id: str, body: RescheduleRequest, actor: Actor, uow: UoW, clock: Clock):
    appt = RescheduleAppointment(uow, clock).execute(
        actor, AppointmentId.parse(appointment_id), body.new_start
    )
    return ser_appointment(appt)


@router.post("/{appointment_id}/confirm", response_model=AppointmentResponse)
def confirm(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    return ser_appointment(
        ConfirmAppointment(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    )


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    return ser_appointment(
        CancelAppointment(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    )


@router.post("/{appointment_id}/no-show", response_model=AppointmentResponse)
def no_show(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    return ser_appointment(
        MarkNoShow(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    )


@router.put("/{appointment_id}/fee", response_model=AppointmentResponse)
def adjust_fee(appointment_id: str, body: ChargeRequest, actor: Actor, uow: UoW, clock: Clock):
    return ser_appointment(AdjustAppointmentFee(uow, clock).execute(
        actor, AppointmentId.parse(appointment_id), fee(body.amount), body.note,
    ))


@router.get("/{appointment_id}/vitals", response_model=AppointmentVitalsResponse)
def get_appointment_vitals(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    view = GetAppointmentVitals(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    return ser_appointment_vitals(view)


@router.put("/{appointment_id}/vitals", response_model=AppointmentVitalsResponse)
def update_appointment_vitals(
    appointment_id: str, body: VitalsUpdateRequest, actor: Actor, uow: UoW, clock: Clock
):
    view = UpdateAppointmentVitals(uow, clock).execute(
        actor, AppointmentId.parse(appointment_id), vital_changes(body)
    )
    return ser_appointment_vitals(view)
