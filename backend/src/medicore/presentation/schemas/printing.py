"""Schemas of the printable documents: the sheet's header plus what each one shows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from medicore.domain.enums import PaperSize


class PrintClinicSchema(BaseModel):
    name: str
    tax_id: str
    location_name: str
    address: str | None
    phone: str | None
    paper: PaperSize
    letterhead: bool


class PrintDoctorSchema(BaseModel):
    name: str
    specialty: str | None
    jvpm: str | None
    sex: str | None


class PrintPatientSchema(BaseModel):
    name: str
    code: str
    sex: str
    date_of_birth: date
    age: int
    allergies: list[str]


class PrintContextSchema(BaseModel):
    clinic: PrintClinicSchema
    printed_at: datetime
    patient: PrintPatientSchema | None = None
    doctor: PrintDoctorSchema | None = None


class RecordPrintResponse(BaseModel):
    context: PrintContextSchema
    record: dict[str, Any]
    indications: str | None
    amends_code: str | None


class CertificatePrintResponse(BaseModel):
    context: PrintContextSchema
    certificate: dict[str, Any]
    encounter_at: datetime
    ended_at: datetime


class ProcedurePrintResponse(BaseModel):
    context: PrintContextSchema
    procedure: dict[str, Any]


class AppointmentPrintResponse(BaseModel):
    context: PrintContextSchema
    appointment: dict[str, Any]


class AgendaRowSchema(BaseModel):
    code: str
    scheduled_start: datetime
    duration_minutes: int
    type: str
    status: str
    reason: str
    patient_name: str
    patient_code: str


class AgendaPrintResponse(BaseModel):
    context: PrintContextSchema
    day: date
    rows: list[AgendaRowSchema]
