"""Audit-trail router (tenant admin)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.audit import ListTenantAudit
from medicore.domain.repositories._support import AuditFilter, Paging
from medicore.presentation.dependencies import Actor, UoW
from medicore.presentation.schemas.platform import AuditListResponse
from medicore.presentation.serializers import ser_audit

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditListResponse)
def list_audit(
    actor: Actor,
    uow: UoW,
    action: str | None = Query(None),
    category: str | None = Query(None),
    entity_type: str | None = Query(None),
    actor_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    with uow:
        f = AuditFilter(
            action=action,
            category=category,
            entity_type=entity_type,
            actor_id=actor_id,
            date_from=date_from,
            date_to=date_to,
        )
        page = ListTenantAudit(uow).execute(actor, f, Paging(offset=offset, limit=limit))
        # Resolve actor names with per-id caching (mirrors _ser_appointments).
        names: dict = {}
        for e in page.items:
            if e.actor_id not in names:
                u = uow.users.get_by_id(e.actor_id)
                names[e.actor_id] = u.name if u else None
        return AuditListResponse(
            items=[{**ser_audit(e), "actor_name": names[e.actor_id]} for e in page.items],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
        )
