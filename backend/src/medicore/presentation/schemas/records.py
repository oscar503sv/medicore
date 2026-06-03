"""Medical record and document schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AmendRequest(BaseModel):
    chief_complaint: str | None = None
    soap: dict[str, str] | None = None


class UploadDocumentRequest(BaseModel):
    patient_id: str
    file_name: str
    kind: str
    mime_type: str
    size_bytes: int
    storage_key: str
    record_id: str | None = None


class RecordResponse(BaseModel):
    id: str
    tenant_id: str
    code: str
    patient_id: str
    patient_name: str | None = None
    author_id: str
    type: str
    status: str
    encounter_at: datetime
    location_name: str
    chief_complaint: str
    soap: dict[str, Any]
    vitals: dict[str, Any]
    diagnoses: list[dict[str, Any]]
    prescriptions: list[dict[str, Any]]
    vaccines: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    signed_at: datetime
    signed_by_id: str
    appointment_id: str | None
    consultation_id: str | None
    amends_record_id: str | None


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    patient_id: str
    file_name: str
    kind: str
    mime_type: str
    size_bytes: int
    storage_key: str
    uploaded_by_id: str
    uploaded_at: datetime
    record_id: str | None
