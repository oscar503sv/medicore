"""Insurer schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateInsurerRequest(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_person: str | None = None
    notes: str | None = None


class UpdateInsurerRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_person: str | None = None
    notes: str | None = None


class InsurerResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    phone: str | None
    email: str | None
    address: str | None
    contact_person: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class InsurerListResponse(BaseModel):
    items: list[InsurerResponse]
