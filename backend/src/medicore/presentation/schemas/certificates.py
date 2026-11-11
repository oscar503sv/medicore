"""Medical certificate schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from medicore.domain.entities.medical_certificate import (
    ADDRESSEE_MAX,
    MAX_REST_DAYS,
    REMARKS_MAX,
    VOID_REASON_MAX,
)
from medicore.domain.enums import CertificateKind


class IssueCertificateRequest(BaseModel):
    kind: CertificateKind
    rest_from: date | None = None
    rest_days: int | None = Field(None, ge=1, le=MAX_REST_DAYS)
    include_diagnosis: bool = False
    remarks: str | None = Field(None, max_length=REMARKS_MAX)
    addressee: str | None = Field(None, max_length=ADDRESSEE_MAX)


class VoidCertificateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=VOID_REASON_MAX)


class CertificateResponse(BaseModel):
    id: str
    code: str
    patient_id: str
    record_id: str
    doctor_id: str
    doctor_name: str | None = None
    kind: CertificateKind
    issued_at: datetime
    rest_from: date | None
    rest_days: int | None
    rest_until: date | None
    diagnosis: str | None
    remarks: str | None
    addressee: str | None
    voided_at: datetime | None
    void_reason: str | None
