"""In-clinic medication application request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from medicore.domain.enums import ApplicationOutcome, ApplicationRoute, ApplicationSite


class ApplicationRecordResponse(BaseModel):
    id: str
    order_id: str
    dose_number: int
    outcome: str
    recorded_at: datetime
    recorded_by_name: str | None
    lot: str | None
    lot_expiry: date | None
    site: str | None
    blood_pressure: str | None
    temperature: float | None
    allergy_override: str | None
    notes: str | None
    observe_until: datetime | None
    observation_closed_at: datetime | None
    observation_closed_by_name: str | None
    reaction: bool | None
    reaction_notes: str | None
    voided_at: datetime | None
    voided_by_name: str | None
    void_reason: str | None


class ApplicationOrderResponse(BaseModel):
    id: str
    patient_id: str
    drug: str
    dose: str
    route: str
    source: str
    status: str
    starts_at: datetime
    doses_total: int
    interval_hours: int | None
    observation_minutes: int
    instructions: str | None
    ordered_by_name: str | None
    external_prescriber: str | None
    external_jvpm: str | None
    created_by_name: str | None
    created_at: datetime
    cancelled_at: datetime | None
    cancelled_by_name: str | None
    cancel_reason: str | None
    next_dose: int | None
    next_due_at: datetime | None
    allergy_conflicts: list[str]
    records: list[ApplicationRecordResponse]


class WorklistPatient(BaseModel):
    id: str
    code: str
    name: str
    age: int
    allergies: list[str]


class DueItemResponse(BaseModel):
    patient: WorklistPatient
    order: ApplicationOrderResponse
    late: bool


class RecordItemResponse(BaseModel):
    patient: WorklistPatient
    order: ApplicationOrderResponse
    record: ApplicationRecordResponse


class ApplicationWorklistResponse(BaseModel):
    now: datetime
    due: list[DueItemResponse]
    observing: list[RecordItemResponse]
    done_today: list[RecordItemResponse]


class ExternalOrderRequest(BaseModel):
    patient_id: str
    drug: str = Field(min_length=1, max_length=120)
    dose: str = Field(min_length=1, max_length=60)
    route: ApplicationRoute
    prescriber: str = Field(min_length=1, max_length=120)
    jvpm: str = Field(min_length=1, max_length=10)
    doses_total: int = Field(1, ge=1, le=30)
    interval_hours: int | None = Field(None, ge=1, le=168)
    observation_minutes: int = Field(30, ge=0, le=240)
    instructions: str | None = Field(None, max_length=500)


class RecordApplicationRequest(BaseModel):
    outcome: ApplicationOutcome = ApplicationOutcome.APPLIED
    lot: str | None = Field(None, max_length=60)
    lot_expiry: date | None = None
    site: ApplicationSite | None = None
    blood_pressure: str | None = Field(None, max_length=10)
    temperature: float | None = None
    allergy_override: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=500)


class CloseObservationRequest(BaseModel):
    reaction: bool
    notes: str | None = Field(None, max_length=500)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
