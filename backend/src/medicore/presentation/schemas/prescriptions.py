"""Prescription schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class PrescriptionResponse(BaseModel):
    id: str
    patient_id: str
    prescriber_id: str
    prescriber_name: str | None
    drug: str
    dose: str
    schedule: str
    start_date: date
    end_date: date | None
    duration_days: int | None
    status: str
    record_id: str | None
    created_at: datetime


class PrescriptionListResponse(BaseModel):
    items: list[PrescriptionResponse]
