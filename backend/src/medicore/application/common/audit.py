"""Helper to build AuditLog entries for sensitive operations (HIPAA/GDPR traceability)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.shared.identifiers import AuditLogId, TenantId, UserId

PLATFORM_SUPPORT = "platform_support"
AUDIT_COALESCE_WINDOW = timedelta(minutes=10)


def subject(*parts: object) -> str:
    """Human-readable label for the entity an action targets, e.g. "P-00013 · Lucía Álvarez".

    Joins the truthy parts with " · ". Stored in audit metadata as ``subject`` so the audit
    UI can show a meaningful Detail column without exposing raw UUIDs.
    """
    return " · ".join(str(p) for p in parts if p)


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


def _as_utc(moment: datetime) -> datetime:
    # The database hands timestamps back in the session's zone; compare instants, not
    # wall-clocks. A naive value (tests' FixedClock) is taken as it is.
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment


def append_coalesced(
    uow: UnitOfWork,
    entry: AuditLog,
    keys: Iterable[str],
    window: timedelta = AUDIT_COALESCE_WINDOW,
) -> bool:
    """Append ``entry`` unless the same actor already logged this action on this entity
    within ``window`` covering the same ``keys``; returns whether it was written.

    Autosave fires every few seconds and the log is append-only: one entry per section
    first touched in a window keeps the trail readable without losing who changed what.
    ``keys`` are names (sections, vital fields), never text.
    """
    wanted = sorted(set(keys))
    last = uow.audit.last_for(entry.entity_type, entry.entity_id, entry.action, entry.actor_id)
    if (
        last is not None
        and _as_utc(entry.timestamp) - _as_utc(last.timestamp) < window
        and set(wanted) <= set(last.metadata.get("keys", ()))  # type: ignore[call-overload]
    ):
        return False
    entry.metadata["keys"] = wanted
    uow.audit.append(entry)
    return True


def platform_audit_entry(
    actor: PlatformActorContext,
    when: datetime,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    tenant_id: TenantId | None = None,
    **metadata: object,
) -> PlatformAuditLog:
    """An entry for the platform (superadmin) trail; ``tenant_id`` links it to a clinic."""
    return PlatformAuditLog(
        id=AuditLogId.new(),
        actor_id=actor.admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=dict(metadata),
        timestamp=when,
        tenant_id=tenant_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
    )


def support_audit_entry(
    actor: PlatformActorContext,
    tenant_id: TenantId,
    when: datetime,
    action: str,
    entity_type: str,
    entity_id: str,
    **metadata: object,
) -> AuditLog:
    """Clinic-trail copy of a console action on the clinic's accounts, so the clinic sees
    what platform support did. The actor is the superadmin's id; no email or name leaves
    the platform."""
    return AuditLog(
        id=AuditLogId.new(),
        tenant_id=tenant_id,
        actor_id=UserId(actor.admin_id.value),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={**metadata, "via": PLATFORM_SUPPORT},
        timestamp=when,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
    )
