"""Platform (superadmin) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlatformLoginRequest(BaseModel):
    email: str
    password: str


class PlatformSessionResponse(BaseModel):
    token: str
    admin_id: str
    name: str
    email: str


class PlatformAdminResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_initials: str
    last_seen_at: datetime | None = None


class LocationResponse(BaseModel):
    id: str
    name: str
    address: str | None = None
    is_primary: bool


class TenantResponse(BaseModel):
    id: str
    legal_name: str
    tax_id: str
    slug: str
    timezone: str
    plan: str
    seat_limit: int
    status: str
    icd_version: str
    locations: list[LocationResponse]


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int
    offset: int
    limit: int


class CreateTenantRequest(BaseModel):
    legal_name: str
    tax_id: str
    slug: str
    timezone: str = "Europe/Madrid"
    icd_version: str = "cie11"
    location_name: str
    admin_name: str
    admin_email: str
    admin_password: str


class CreateTenantResponse(BaseModel):
    tenant: TenantResponse
    admin_user_id: str
    admin_email: str


class UpdateTenantRequest(BaseModel):
    legal_name: str | None = None
    tax_id: str | None = None
    timezone: str | None = None
    plan: str | None = None
    seat_limit: int | None = None
    icd_version: str | None = None


class SetTenantStatusRequest(BaseModel):
    status: str  # active | suspended | archived
