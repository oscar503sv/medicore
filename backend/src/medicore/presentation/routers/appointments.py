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
    GetBookingOptions,
    GetWeeklySchedule,
    ListAppointmentsForDay,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.domain.enums import AppointmentType
from medicore.domain.shared.identifiers import (
    AppointmentId,
    InsurerId,
    LocationId,
    PatientId,
    UserId,
)
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.appointments import (
    AppointmentResponse,
    BookingOptionsResponse,
    CreateAppointmentRequest,
    RescheduleRequest,
    SlotResponse,
    WeeklyScheduleResponse,
)
from medicore.presentation.serializers import ser_appointment, ser_slot, ser_user

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _ser_appointments(uow: UoW, appts: list) -> list[dict]:
    """Serialize appointments, resolving patient/doctor/insurer names with per-id caching."""
    patient_names: dict = {}
    doctor_names: dict = {}
    insurer_names: dict = {}
    for a in appts:
        if a.patient_id not in patient_names:
            patient = uow.patients.get_by_id(a.patient_id)
            patient_names[a.patient_id] = patient.full_name if patient else None
        if a.doctor_id not in doctor_names:
            doctor = uow.users.get_by_id(a.doctor_id)
            doctor_names[a.doctor_id] = doctor.name if doctor else None
        if a.insurance_id and a.insurance_id not in insurer_names:
            insurer = uow.insurers.get_by_id(a.insurance_id)
            insurer_names[a.insurance_id] = insurer.name if insurer else None
    return [
        ser_appointment(
            a,
            patient_name=patient_names[a.patient_id],
            doctor_name=doctor_names[a.doctor_id],
            insurer_name=insurer_names.get(a.insurance_id) if a.insurance_id else None,
        )
        for a in appts
    ]


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
    )


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
        return _ser_appointments(uow, appts)


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
                d.isoformat(): _ser_appointments(uow, appts) for d, appts in schedule.items()
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
        reason=body.reason,
        room=body.room,
        insurance_id=InsurerId.parse(body.insurance_id) if body.insurance_id else None,
    )
    appt = CreateAppointment(uow, codes, clock).execute(actor, cmd)
    return ser_appointment(appt)


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
