"""Appointments router."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    GetAvailableSlots,
    GetWeeklySchedule,
    ListAppointmentsForDay,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.domain.enums import AppointmentType
from medicore.domain.shared.identifiers import AppointmentId, LocationId, PatientId, UserId
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.appointments import (
    AppointmentResponse,
    CreateAppointmentRequest,
    RescheduleRequest,
    SlotResponse,
    WeeklyScheduleResponse,
)
from medicore.presentation.serializers import ser_appointment, ser_slot

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentResponse])
def list_for_day(
    actor: Actor,
    uow: UoW,
    on: date = Query(...),
    doctor_id: str | None = Query(None),
):
    with uow:
        did = UserId.parse(doctor_id) if doctor_id else None
        appts = ListAppointmentsForDay(uow).execute(actor, on, did)
    return [ser_appointment(a) for a in appts]


@router.get("/schedule", response_model=WeeklyScheduleResponse)
def weekly_schedule(
    actor: Actor,
    uow: UoW,
    week_start: date = Query(...),
    doctor_id: str | None = Query(None),
):
    with uow:
        did = UserId.parse(doctor_id) if doctor_id else None
        schedule = GetWeeklySchedule(uow).execute(actor, week_start, did)
    return WeeklyScheduleResponse(
        schedule={
            d.isoformat(): [ser_appointment(a) for a in appts] for d, appts in schedule.items()
        }
    )


@router.get("/slots", response_model=list[SlotResponse])
def available_slots(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    doctor_id: str = Query(...),
    on: date = Query(...),
):
    with uow:
        slots = GetAvailableSlots(uow, clock).execute(actor, UserId.parse(doctor_id), on)
    return [ser_slot(s) for s in slots]


@router.post("", response_model=AppointmentResponse, status_code=201)
def create_appointment(
    body: CreateAppointmentRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock
):
    cmd = CreateAppointmentCommand(
        patient_id=PatientId.parse(body.patient_id),
        doctor_id=UserId.parse(body.doctor_id),
        location_id=LocationId.parse(body.location_id),
        type=AppointmentType(body.type),
        scheduled_start=body.scheduled_start,
        duration_minutes=body.duration_minutes,
        reason=body.reason,
        room=body.room,
    )
    appt = CreateAppointment(uow, codes, clock).execute(actor, cmd)
    return ser_appointment(appt)


@router.put("/{appointment_id}/reschedule", response_model=AppointmentResponse)
def reschedule(appointment_id: str, body: RescheduleRequest, actor: Actor, uow: UoW, clock: Clock):
    appt = RescheduleAppointment(uow, clock).execute(
        actor, AppointmentId.parse(appointment_id), body.new_start, body.new_duration
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
