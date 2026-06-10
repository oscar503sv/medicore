"""Availability schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class TimeRangeSchema(BaseModel):
    start: str  # "HH:MM"
    end: str


class WeeklyDayRequest(BaseModel):
    day_of_week: int
    enabled: bool
    blocks: list[TimeRangeSchema] = []


class ExceptionRequest(BaseModel):
    date: date
    kind: str  # off | extra
    reason: str = ""
    blocks: list[TimeRangeSchema] = []


class BookingRulesRequest(BaseModel):
    slot_minutes: int = 30
    min_advance_hours: int = 0
    allow_same_day: bool = True


class AvailabilityResponse(BaseModel):
    id: str
    doctor_id: str
    weekly: list[dict]
    exceptions: list[dict]
    rules: dict


class PreviewResponse(BaseModel):
    preview: dict[str, list[dict]]  # date ISO → list of slots
