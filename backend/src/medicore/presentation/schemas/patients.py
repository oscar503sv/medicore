"""Patient schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class ContactInfoSchema(BaseModel):
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class CreatePatientRequest(BaseModel):
    first_name: str
    last_name: str
    sex: str
    date_of_birth: date
    contact: ContactInfoSchema = ContactInfoSchema()
    blood_type: str | None = None
    primary_doctor_id: str | None = None
    tags: list[str] = []
    allergies: list[str] = []


class UpdatePatientRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    contact: ContactInfoSchema | None = None
    blood_type: str | None = None
    primary_doctor_id: str | None = None
    tags: list[str] | None = None
    allergies: list[str] | None = None


class PatientResponse(BaseModel):
    id: str
    tenant_id: str
    code: str
    first_name: str
    last_name: str
    sex: str
    date_of_birth: date
    age: int
    blood_type: str | None
    primary_doctor_id: str | None
    status: str
    tags: list[str]
    allergies: list[str]
    contact: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    next_visit: datetime | None = None


class PatientListResponse(BaseModel):
    items: list[PatientResponse]
    total: int
    offset: int
    limit: int


class PatientDetailResponse(BaseModel):
    patient: PatientResponse
    last_visit: datetime | None
    next_visit: datetime | None
    records_count: int
    active_prescriptions: int
