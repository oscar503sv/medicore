"""Vaccination request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from medicore.domain.enums import (
    InjectionSite,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)


class VaccineResponse(BaseModel):
    code: str
    route: str
    in_schedule: bool


class ScheduledDoseResponse(BaseModel):
    key: str
    vaccine: str
    kind: str
    number: int
    age_months: int
    stage: str
    max_age_months: int | None
    repeat_months: int | None
    routine: bool
    sex: str | None


class VaccinationCatalogResponse(BaseModel):
    schedule: str
    vaccines: list[VaccineResponse]
    doses: list[ScheduledDoseResponse]


class DoseStateResponse(BaseModel):
    key: str
    status: str
    due_on: date | None
    last_on: date | None


class VaccinationRecordResponse(BaseModel):
    id: str
    patient_id: str
    vaccine_code: str
    dose_key: str | None
    outcome: str
    occurred_on: date
    source: str
    lot: str | None
    route: str | None
    site: str | None
    notes: str | None
    recorded_by_id: str
    recorded_by_name: str | None
    created_at: datetime
    voided_at: datetime | None
    voided_by_name: str | None
    void_reason: str | None


class VaccinationCardResponse(BaseModel):
    today: date
    states: list[DoseStateResponse]
    records: list[VaccinationRecordResponse]


class RecordVaccinationRequest(BaseModel):
    vaccine_code: str = Field(min_length=1, max_length=40)
    dose_key: str | None = Field(None, max_length=40)
    outcome: VaccinationOutcome = VaccinationOutcome.ADMINISTERED
    occurred_on: date
    source: VaccinationSource = VaccinationSource.CLINIC
    lot: str | None = Field(None, max_length=60)
    route: VaccineRoute | None = None
    site: InjectionSite | None = None
    notes: str | None = Field(None, max_length=500)


class VoidVaccinationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class WorklistPatient(BaseModel):
    id: str
    code: str
    name: str
    age: int
    date_of_birth: date
    sex: str
    phone: str | None


class WorklistDoseResponse(BaseModel):
    patient: WorklistPatient
    key: str
    vaccine: str
    status: str
    due_on: date | None


class WorklistGivenResponse(BaseModel):
    patient: WorklistPatient
    record: VaccinationRecordResponse


class VaccinationWorklistResponse(BaseModel):
    today: date
    pending: list[WorklistDoseResponse]
    upcoming: list[WorklistDoseResponse]
    given_today: list[WorklistGivenResponse]
