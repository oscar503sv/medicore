"""Shared types for repository ports.

Every repository operates **within an implicit tenant scope** (the multi-tenant golden rule):
implementations must filter by ``tenant_id`` automatically (global query filter) rather than
relying on callers to remember. The interfaces here therefore do not take a ``tenant_id``
parameter on every method — the scope is bound when the repository is constructed/resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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


@dataclass(frozen=True, slots=True)
class AuditFilter:
    action: str | None = None  # exact action, e.g. "record.amended"
    category: str | None = None  # action namespace, e.g. "patient" matches "patient.*"
    entity_type: str | None = None
    actor_id: str | None = None
    date_from: str | None = None  # inclusive day, "YYYY-MM-DD"
    date_to: str | None = None  # inclusive day, "YYYY-MM-DD"
