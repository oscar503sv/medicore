"""Appointment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from medicore.domain.enums import AppointmentType
from medicore.presentation.schemas.organization import LocationResponse
from medicore.presentation.schemas.users import UserResponse


# Duration is never sent by the client — it always comes from the booking rules of whoever
# attends. Exactly one of doctor_id and agenda_id is sent (otherwise 422).
class CreateAppointmentRequest(BaseModel):
    patient_id: str
    doctor_id: str | None = None
    agenda_id: str | None = None
    location_id: str
    type: AppointmentType
    scheduled_start: datetime
    reason: str
    room: str | None = None
    insurance_id: str | None = None


class WalkInRequest(BaseModel):
    patient_id: str
    doctor_id: str | None = None
    agenda_id: str | None = None
    location_id: str | None = None
    type: AppointmentType = AppointmentType.EMERGENCY
    reason: str = Field(min_length=1, max_length=500)
    insurance_id: str | None = None


class RescheduleRequest(BaseModel):
    new_start: datetime


class AppointmentResponse(BaseModel):
    id: str
    tenant_id: str
    code: str
    patient_id: str
    doctor_id: str | None = None  # None when a service agenda attends it
    agenda_id: str | None = None
    agenda_name: str | None = None
    location_id: str
    type: str
    status: str
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int
    reason: str
    room: str | None
    insurance_id: str | None = None
    patient_name: str | None = None
    doctor_name: str | None = None
    insurer_name: str | None = None
    created_by_id: str
    # fee (USD, "25.00"): the doctor's price when booked, what is charged, and why
    listed_fee: str | None = None
    fee: str | None = None
    fee_note: str | None = None
    is_walk_in: bool = False
    created_at: datetime
    updated_at: datetime


class SlotResponse(BaseModel):
    start: datetime
    end: datetime
    status: str  # free | taken | out_of_hours | blocked_rules


class WeeklyScheduleResponse(BaseModel):
    schedule: dict[str, list[AppointmentResponse]]  # date ISO → appointments


class BookingDoctorResponse(UserResponse):
    slot_minutes: int | None = None  # appointment duration imposed by the doctor's rules


class BookingAgendaResponse(BaseModel):
    id: str
    name: str
    kind: str
    location_id: str | None
    slot_minutes: int | None = None  # appointment duration imposed by the agenda's rules


class BookingOptionsResponse(BaseModel):
    doctors: list[BookingDoctorResponse]
    locations: list[LocationResponse]
    agendas: list[BookingAgendaResponse] = []
