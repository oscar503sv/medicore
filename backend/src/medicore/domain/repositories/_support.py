"""Shared types for repository ports.

Every repository operates **within an implicit tenant scope** (the multi-tenant golden rule):
implementations must filter by ``tenant_id`` automatically (global query filter) rather than
relying on callers to remember. The interfaces here therefore do not take a ``tenant_id``
parameter on every method — the scope is bound when the repository is constructed/resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
