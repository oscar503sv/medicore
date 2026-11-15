"""Prescription schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
    closed_at: datetime | None
    closed_by_id: str | None
    cancel_reason: str | None


class CancelPrescriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The domain enforces the real bounds (after stripping); this only caps the payload.
    reason: str = Field(max_length=2000)


class PrescriptionListResponse(BaseModel):
    items: list[PrescriptionResponse]
