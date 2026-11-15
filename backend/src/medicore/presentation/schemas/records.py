"""Medical record and document schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from medicore.domain.enums import DocumentKind


class AmendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The reason's length is judged by the domain (min/max in the error); the cap here only
    # bounds the payload.
    reason: str = Field(max_length=4000)
    chief_complaint: str | None = Field(None, min_length=1, max_length=500)
    note: dict[str, str] | None = None  # section key -> text


class UploadDocumentRequest(BaseModel):
    # Where the file lives is the server's call: a client-sent storage_key is rejected.
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(max_length=64)
    file_name: str = Field(max_length=255)
    kind: DocumentKind
    mime_type: str = Field(max_length=100)
    size_bytes: int
    record_id: str | None = Field(None, max_length=64)


class RecordResponse(BaseModel):
    id: str
    tenant_id: str
    code: str
    patient_id: str
    patient_name: str | None = None
    signed_by_name: str | None = None
    author_id: str
    type: str
    status: str
    encounter_at: datetime
    location_name: str
    insurer_name: str | None = None
    chief_complaint: str
    note: dict[str, Any]
    vitals: dict[str, Any]
    diagnoses: list[dict[str, Any]]
    prescriptions: list[dict[str, Any]]
    vaccines: list[dict[str, Any]]
    exams: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]]
    signed_at: datetime
    signed_by_id: str
    appointment_id: str | None
    consultation_id: str | None
    amends_record_id: str | None
    amendment_reason: str | None = None
    is_current: bool = True
    superseded_by_id: str | None = None


class RecordVersionResponse(BaseModel):
    id: str
    version: int
    status: str
    signed_at: datetime
    signed_by_id: str
    signed_by_name: str | None = None
    amendment_reason: str | None = None
    is_current: bool


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    patient_id: str
    file_name: str
    kind: str
    mime_type: str
    size_bytes: int
    uploaded_by_id: str
    uploaded_at: datetime
    record_id: str | None


class RecordSummaryResponse(BaseModel):
    id: str
    code: str
    patient_id: str
    patient_name: str | None = None
    type: str
    status: str
    encounter_at: datetime
    location_name: str
    signed_by_id: str
    signed_by_name: str | None = None
    consultation_id: str | None
    amends_record_id: str | None


class RecordListResponse(BaseModel):
    items: list[RecordSummaryResponse]
    total: int
    offset: int
    limit: int


class VitalsReadingResponse(BaseModel):
    record_id: str
    record_code: str
    encounter_at: datetime
    vitals: dict[str, Any]
