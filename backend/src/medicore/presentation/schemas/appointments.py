"""Appointment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateAppointmentRequest(BaseModel):
    patient_id: str
    doctor_id: str
    location_id: str
    type: str
    scheduled_start: datetime
    duration_minutes: int
    reason: str
    room: str | None = None


class RescheduleRequest(BaseModel):
    new_start: datetime
    new_duration: int | None = None


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
    created_by_id: str
    created_at: datetime
    updated_at: datetime


class SlotResponse(BaseModel):
    start: datetime
    end: datetime
    status: str  # free | taken | out_of_hours


class WeeklyScheduleResponse(BaseModel):
    schedule: dict[str, list[AppointmentResponse]]  # date ISO → appointments
