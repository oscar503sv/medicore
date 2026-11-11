"""Platform console · Monitoring schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class RuntimeResponse(BaseModel):
    version: str
    commit: str | None
    environment: str
    python: str
    started_at: datetime
    uptime_seconds: int


class ConnectionsResponse(BaseModel):
    total: int
    active: int
    idle: int
    idle_in_transaction: int
    max_connections: int


class DatabaseResponse(BaseModel):
    version: str
    size_bytes: int
    revision: str | None
    latency_ms: float
    connections: ConnectionsResponse


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


class ConsoleLoginResponse(BaseModel):
    admin_name: str | None
    action: str
    at: datetime
    ip_address: str | None
    user_agent: str | None


class LoginsResponse(BaseModel):
    failing_accounts: int
    failed_attempts: int
    lockouts_24h: int
    locked: list[LockedLoginResponse]
    console: list[ConsoleLoginResponse]


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
    first_at: datetime | None
    first_commit: str | None
    last_commit: str | None


class DayCount(BaseModel):
    day: date
    count: int


class ErrorsResponse(BaseModel):
    last_24h: int
    last_7d: int
    retention_days: int
    groups: list[ErrorGroupResponse]
    daily: list[DayCount]


class JobResponse(BaseModel):
    job: str
    state: str  # ok | failed | overdue | never
    expected_every_hours: float | None
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_ok: bool | None
    last_detail: str | None
    last_success_at: datetime | None


class RoutePerformanceResponse(BaseModel):
    method: str
    route: str
    count: int
    client_errors: int
    server_errors: int
    avg_ms: float
    p95_ms: float | None
    max_ms: float


class HourVolumeResponse(BaseModel):
    hour: datetime
    count: int
    server_errors: int


class PerformanceResponse(BaseModel):
    window_hours: int
    requests: int
    client_errors: int
    server_errors: int
    p50_ms: float | None
    p95_ms: float | None
    slowest: list[RoutePerformanceResponse]
    hourly: list[HourVolumeResponse]


class SystemStatusResponse(BaseModel):
    now: datetime
    runtime: RuntimeResponse
    database: DatabaseResponse
    largest_tables: list[TableSizeResponse]
    logins: LoginsResponse
    sessions: dict[str, int]
    impersonations: list[ImpersonationResponse]
    errors: ErrorsResponse
    jobs: list[JobResponse]
    performance: PerformanceResponse


class ErrorEventResponse(BaseModel):
    id: str
    occurred_at: datetime
    method: str
    route: str
    status: int
    error_type: str
    location: str
    commit: str | None


class ErrorEventListResponse(BaseModel):
    items: list[ErrorEventResponse]
    total: int
    offset: int
    limit: int
