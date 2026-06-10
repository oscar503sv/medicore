"""Appointment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from medicore.presentation.schemas.organization import LocationResponse
from medicore.presentation.schemas.users import UserResponse


# Duration is never sent by the client — it always comes from the doctor's booking rules.
class CreateAppointmentRequest(BaseModel):
    patient_id: str
    doctor_id: str
    location_id: str
    type: str
    scheduled_start: datetime
    reason: str
    room: str | None = None
    insurance_id: str | None = None


class RescheduleRequest(BaseModel):
    new_start: datetime


class AppointmentResponse(BaseModel):
    id: str
    tenant_id: str
    code: str
    patient_id: str
    doctor_id: str
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


class BookingOptionsResponse(BaseModel):
    doctors: list[BookingDoctorResponse]
    locations: list[LocationResponse]
