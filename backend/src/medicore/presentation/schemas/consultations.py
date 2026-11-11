"""Consultation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from medicore.domain.enums import ApplicationRoute


class VitalsSchema(BaseModel):
    blood_pressure: str | None = None
    heart_rate: int | None = None
    spo2: int | None = None
    temperature: str | None = None
    weight: str | None = None
    glucose: int | None = None
    height: str | None = None
    fetal_heart_rate: int | None = None


class SoapSchema(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class AutosaveRequest(BaseModel):
    vitals: VitalsSchema | None = None
    soap: SoapSchema | None = None


class DiagnosisRequest(BaseModel):
    code: str
    label: str


class PrescriptionDraftRequest(BaseModel):
    drug: str
    dose: str
    schedule: str
    duration_days: int | None = None


class ApplicationDraftRequest(BaseModel):
    drug: str = Field(min_length=1, max_length=120)
    dose: str = Field(min_length=1, max_length=60)
    route: ApplicationRoute
    doses_total: int = Field(1, ge=1, le=30)
    interval_hours: int | None = Field(None, ge=1, le=168)
    observation_minutes: int = Field(30, ge=0, le=240)
    instructions: str | None = Field(None, max_length=500)


class ProcedureDraftRequest(BaseModel):
    type_id: str
    indication: str = Field(min_length=1, max_length=500)
    included: bool = False  # included in the consultation fee


class SignRequest(BaseModel):
    chief_complaint: str = ""


class ConsultationResponse(BaseModel):
    id: str
    tenant_id: str
    appointment_id: str
    patient_id: str
    doctor_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    vitals: dict[str, Any]
    soap: dict[str, Any]
    diagnoses: list[dict[str, Any]]
    draft_prescriptions: list[dict[str, Any]]
    draft_applications: list[dict[str, Any]] = []
    draft_procedures: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]]
    completion_percent: int
    last_saved_at: datetime | None
    # Context for the live consultation header (patient summary + booked appointment).
    patient: dict[str, Any] | None = None
    appointment: dict[str, Any] | None = None
