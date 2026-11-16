"""Service agenda schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from medicore.domain.entities.service_agenda import MAX_NAME_LENGTH
from medicore.domain.enums import ServiceAgendaKind


class CreateServiceAgendaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    kind: ServiceAgendaKind = ServiceAgendaKind.VACCINATION
    location_id: str | None = None


class UpdateServiceAgendaRequest(BaseModel):
    """Only the fields sent change; ``location_id: null`` clears the default location."""

    name: str | None = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    location_id: str | None = None


class ServiceAgendaActiveRequest(BaseModel):
    active: bool


class ServiceAgendaResponse(BaseModel):
    id: str
    name: str
    kind: str
    location_id: str | None
    active: bool
    slot_minutes: int | None = None  # None → no schedule configured yet
    created_at: datetime
    updated_at: datetime
