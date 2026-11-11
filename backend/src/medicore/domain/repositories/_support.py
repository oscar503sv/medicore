"""Shared types for repository ports.

Every repository operates **within an implicit tenant scope** (the multi-tenant golden rule):
implementations must filter by ``tenant_id`` automatically (global query filter) rather than
relying on callers to remember. The interfaces here therefore do not take a ``tenant_id``
parameter on every method — the scope is bound when the repository is constructed/resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Page[T]:
    """A page of results plus the total count for pagination UIs."""

    items: list[T]
    total: int
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True)
class Paging:
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True)
class PatientFilter:
    status: str | None = None  # PatientStatus value
    doctor_id: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UserFilter:
    role: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class TenantFilter:
    status: str | None = None  # TenantStatus value


@dataclass(frozen=True, slots=True)
class RecordFilter:
    patient_id: str | None = None
    type: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GlobalAuditRow:
    """A consolidated audit row for the platform console, merging the tenant and platform trails.

    ``source_kind`` is ``"platform"`` for superadmin actions or ``"tenant"`` for in-clinic
    activity; ``clinic_name`` is the affected clinic (when known). Names are pre-resolved so the
    presentation layer renders a human-readable timeline without extra lookups.
    """

    id: str
    timestamp: datetime
    source_kind: str  # "tenant" | "platform"
    actor_name: str | None
    action: str
    clinic_name: str | None
    metadata: dict[str, object]
    ip_address: str | None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class AuditFilter:
    action: str | None = None  # exact action, e.g. "record.amended"
    category: str | None = None  # action namespace, e.g. "patient" matches "patient.*"
    entity_type: str | None = None
    actor_id: str | None = None
    date_from: str | None = None  # inclusive day, "YYYY-MM-DD"
    date_to: str | None = None  # inclusive day, "YYYY-MM-DD"


@dataclass(frozen=True, slots=True)
class TenantActivity:
    """How much a clinic is using Medicore, from its audit trail and signed records."""

    last_activity: datetime | None = None
    active_users: int = 0  # distinct people with audited activity in the window
    signed_records: int = 0  # records signed in the window


@dataclass(frozen=True, slots=True)
class PaymentSummary:
    """One subscription payment, as the business overview needs it."""

    tenant_id: str
    amount: Decimal
    paid_on: date


# ── Platform monitoring (read-model rows) ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DatabaseStatus:
    version: str
    size_bytes: int
    revision: str | None  # applied Alembic migration


@dataclass(frozen=True, slots=True)
class TableSize:
    name: str
    size_bytes: int  # table + indexes + TOAST
    rows: int  # planner estimate


@dataclass(frozen=True, slots=True)
class LockedLogin:
    scope: str  # "tenant" | "platform"
    clinic_slug: str | None
    email: str
    failed_count: int
    locked_until: datetime


@dataclass(frozen=True, slots=True)
class LoginPressure:
    failing_accounts: int  # identifiers with failures since the cutoff and no later success
    failed_attempts: int  # those failures, summed
    locked: list[LockedLogin] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ActiveImpersonation:
    session_id: str
    admin_name: str | None
    tenant_id: str | None
    clinic_name: str | None
    started_at: datetime
    expires_at: datetime
    ip_address: str | None


@dataclass(frozen=True, slots=True)
class ErrorGroup:
    method: str
    route: str
    error_type: str
    location: str
    count: int
    last_at: datetime
    first_at: datetime | None = None
    first_commit: str | None = None  # deploy in which it was first seen (within the window)
    last_commit: str | None = None  # deploy of its latest occurrence


@dataclass(frozen=True, slots=True)
class ConnectionStats:
    total: int
    active: int
    idle: int
    idle_in_transaction: int
    max_connections: int


@dataclass(frozen=True, slots=True)
class ConsoleLogin:
    admin_name: str | None
    action: str  # auth.platform_login | auth.platform_login_failed | auth.platform_login_locked
    at: datetime
    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class JobSummary:
    job: str
    last_started_at: datetime
    last_finished_at: datetime
    last_ok: bool
    last_detail: str
    last_success_at: datetime | None


@dataclass(frozen=True, slots=True)
class RequestStatsRow:
    """Requests of one route in one hour, as recorded (and summed across workers)."""

    hour: datetime
    method: str
    route: str
    count: int
    client_errors: int  # 4xx
    server_errors: int  # 5xx
    total_ms: float
    max_ms: float
    buckets: tuple[int, ...]  # LatencyHistogram counts
