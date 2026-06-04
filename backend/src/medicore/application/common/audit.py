"""Helper to build AuditLog entries for sensitive operations (HIPAA/GDPR traceability)."""

from __future__ import annotations

from datetime import datetime

from medicore.application.common.context import ActorContext
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.shared.identifiers import AuditLogId


def audit_entry(
    actor: ActorContext,
    when: datetime,
    action: str,
    entity_type: str,
    entity_id: str,
    **metadata: object,
) -> AuditLog:
    meta = dict(metadata)
    if actor.impersonated_by is not None:
        meta["impersonated_by"] = str(actor.impersonated_by)
    return AuditLog(
        id=AuditLogId.new(),
        tenant_id=actor.tenant_id,
        actor_id=actor.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=meta,
        timestamp=when,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
    )
