"""AuditLog aggregate — traceability for sensitive access/changes (HIPAA/GDPR)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.shared.identifiers import AuditLogId, TenantId, UserId


@dataclass(frozen=True, slots=True)
class AuditLog:
    """An append-only audit entry.

    Record at least: medical-record signing, patient-data access, availability changes,
    and user management.
    """

    id: AuditLogId
    tenant_id: TenantId
    actor_id: UserId
    action: str  # e.g. "record.signed", "patient.viewed"
    entity_type: str
    entity_id: str
    metadata: dict[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    ip_address: str | None = None
    user_agent: str | None = None
