"""PlatformAuditLog — append-only trail of superadmin (platform-level) actions.

Mirrors :class:`AuditLog` but is **not tenant-scoped**: the actor is a platform admin and the
affected entity is usually a tenant (or a user inside one). Kept in a separate table from the
per-tenant ``audit_logs`` so platform actions never depend on a tenant row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from medicore.domain.shared.identifiers import AuditLogId, PlatformAdminId


@dataclass(frozen=True, slots=True)
class PlatformAuditLog:
    id: AuditLogId
    actor_id: PlatformAdminId
    action: str  # e.g. "tenant.created", "tenant.suspended", "user.password_reset"
    entity_type: str  # e.g. "Tenant", "User", "PlatformAdmin"
    entity_id: str
    timestamp: datetime
    metadata: dict[str, object] = field(default_factory=dict)
