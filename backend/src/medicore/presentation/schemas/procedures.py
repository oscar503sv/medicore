"""Minor procedures request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from medicore.domain.enums import ProcedurePerformer


class ProcedureTypeResponse(BaseModel):
    id: str
    name: str
    performer: str
    requires_consent: bool
    follow_up_days: int | None
    takes_specimen: bool
    technique_template: str | None
    instructions_template: str | None
    active: bool
    price: str | None  # USD "25.00"; None: no price set


class ProcedureTypeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    performer: ProcedurePerformer
    requires_consent: bool = False
    follow_up_days: int | None = Field(None, ge=1, le=365)
    takes_specimen: bool = False
    technique_template: str | None = Field(None, max_length=2000)
    instructions_template: str | None = Field(None, max_length=1000)
    price: Decimal | None = None


class ActiveRequest(BaseModel):
    active: bool


class AmendmentResponse(BaseModel):
    at: datetime
    by_name: str | None
    text: str
    reason: str


class ProcedurePatient(BaseModel):
    id: str
    code: str
    name: str
    age: int
    allergies: list[str]


class ProcedureResponse(BaseModel):
    id: str
    patient_id: str
    type_id: str
    type_name: str
    performer: str
    requires_consent: bool
    source: str
    indication: str
    ordered_by_name: str | None
    created_by_name: str | None
    follow_up_days: int | None
    takes_specimen: bool
    consultation_id: str | None
    appointment_id: str | None
    created_at: datetime
    status: str
    allergies_reviewed: bool
    anticoagulants: bool | None
    fasting: bool | None
    allergy_override: str | None
    consent_signer: str | None
    consent_relationship: str | None
    consent_witness: str | None
    consent_at: datetime | None
    consent_by_name: str | None
    bp_before: str | None
    hr_before: int | None
    spo2_before: int | None
    temp_before: float | None
    bp_after: str | None
    hr_after: int | None
    spo2_after: int | None
    temp_after: float | None
    anesthesia: str | None
    technique: str | None
    findings: str | None
    materials: str | None
    complications: str | None
    instructions: str | None
    specimen_sent: bool
    specimen_description: str | None
    started_at: datetime | None
    performed_at: datetime | None
    performed_by_name: str | None
    follow_up_on: date | None
    cancelled_at: datetime | None
    cancelled_by_name: str | None
    cancel_reason: str | None
    amendments: list[AmendmentResponse]
    listed_fee: str | None
    fee: str | None
    fee_note: str | None
    fee_included: bool  # included in the consultation fee


class ProcedureDetailResponse(BaseModel):
    procedure: ProcedureResponse
    patient: ProcedurePatient
    technique_template: str | None
    instructions_template: str | None
    allergy_conflicts: list[str]
    fee_editable: bool  # the actor may change what it is charged


class ProcedureItemResponse(BaseModel):
    patient: ProcedurePatient
    procedure: ProcedureResponse


class AppointmentItemResponse(BaseModel):
    appointment_id: str
    scheduled_start: datetime
    status: str
    reason: str
    doctor_name: str | None
    patient: ProcedurePatient
    procedure: ProcedureResponse | None


class ProcedureWorklistResponse(BaseModel):
    now: datetime
    pending: list[ProcedureItemResponse]
    today: list[AppointmentItemResponse]
    done: list[ProcedureItemResponse]


class CreateProcedureRequest(BaseModel):
    patient_id: str
    type_id: str
    indication: str = Field(min_length=1, max_length=500)
    appointment_id: str | None = None


class ProgressRequest(BaseModel):
    allergies_reviewed: bool = False
    anticoagulants: bool | None = None
    fasting: bool | None = None
    allergy_override: str | None = Field(None, max_length=300)
    bp_before: str | None = Field(None, max_length=10)
    hr_before: int | None = None
    spo2_before: int | None = None
    temp_before: float | None = None
    bp_after: str | None = Field(None, max_length=10)
    hr_after: int | None = None
    spo2_after: int | None = None
    temp_after: float | None = None
    anesthesia: str | None = Field(None, max_length=300)
    technique: str | None = Field(None, max_length=3000)
    findings: str | None = Field(None, max_length=2000)
    materials: str | None = Field(None, max_length=1000)
    complications: str | None = Field(None, max_length=1000)
    instructions: str | None = Field(None, max_length=2000)
    specimen_sent: bool = False
    specimen_description: str | None = Field(None, max_length=500)


class ConsentRequest(BaseModel):
    signer: str = Field(min_length=1, max_length=120)
    relationship: str | None = Field(None, max_length=60)
    witness: str = Field(min_length=1, max_length=120)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class AmendRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=300)
