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
    location_name: str | None = None  # renames the clinic's primary location


class SetTenantStatusRequest(BaseModel):
    status: str  # active | suspended | archived


class TenantStatsResponse(BaseModel):
    tenant_id: str
    legal_name: str
    status: str
    patients: int
    users: int
    appointments: int
    consultations: int
    records: int


class GlobalStatsResponse(BaseModel):
    total_clinics: int
    active_clinics: int
    total_patients: int
    total_users: int
    total_appointments: int
    by_clinic: list[TenantStatsResponse]


class AuditEntryResponse(BaseModel):
    id: str
    tenant_id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    metadata: dict
    timestamp: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    actor_name: str | None = None


class AuditListResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int
    offset: int
    limit: int


class GlobalAuditEntryResponse(BaseModel):
    id: str
    timestamp: datetime
    source_kind: str  # "tenant" | "platform"
    actor_name: str | None = None
    action: str
    clinic_name: str | None = None
    metadata: dict
    ip_address: str | None = None
    user_agent: str | None = None


class GlobalAuditListResponse(BaseModel):
    items: list[GlobalAuditEntryResponse]
    total: int
    offset: int
    limit: int


class ResetPasswordRequest(BaseModel):
    password: str


class UpdateTenantUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None  # admin | doctor | nurse | receptionist
    sex: str | None = None
    phone: str | None = None
    specialty: str | None = None


class ImpersonateRequest(BaseModel):
    reason: str = ""  # why support is entering the clinic; recorded in the audit trail


class ImpersonationResponse(BaseModel):
    token: str
    user_id: str
    tenant_id: str
    tenant_name: str
    timezone: str
    role: str
    name: str
    permissions: list[str] = []
