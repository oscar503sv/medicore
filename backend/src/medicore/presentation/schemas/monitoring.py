"""Platform console · Monitoring schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RuntimeResponse(BaseModel):
    version: str
    commit: str | None
    environment: str
    python: str
    started_at: datetime
    uptime_seconds: int


class DatabaseResponse(BaseModel):
    version: str
    size_bytes: int
    revision: str | None
    latency_ms: float


class TableSizeResponse(BaseModel):
    name: str
    size_bytes: int
    rows: int


class LockedLoginResponse(BaseModel):
    scope: str
    clinic_slug: str | None
    email: str
    failed_count: int
    locked_until: datetime


class LoginsResponse(BaseModel):
    failing_accounts: int
    failed_attempts: int
    lockouts_24h: int
    locked: list[LockedLoginResponse]


class ImpersonationResponse(BaseModel):
    session_id: str
    admin_name: str | None
    tenant_id: str | None
    clinic_name: str | None
    started_at: datetime
    expires_at: datetime
    ip_address: str | None


class ErrorGroupResponse(BaseModel):
    method: str
    route: str
    error_type: str
    location: str
    count: int
    last_at: datetime


class ErrorsResponse(BaseModel):
    last_24h: int
    last_7d: int
    retention_days: int
    groups: list[ErrorGroupResponse]


class SystemStatusResponse(BaseModel):
    now: datetime
    runtime: RuntimeResponse
    database: DatabaseResponse
    largest_tables: list[TableSizeResponse]
    logins: LoginsResponse
    sessions: dict[str, int]
    impersonations: list[ImpersonationResponse]
    errors: ErrorsResponse


class ErrorEventResponse(BaseModel):
    id: str
    occurred_at: datetime
    method: str
    route: str
    status: int
    error_type: str
    location: str


class ErrorEventListResponse(BaseModel):
    items: list[ErrorEventResponse]
    total: int
    offset: int
    limit: int
