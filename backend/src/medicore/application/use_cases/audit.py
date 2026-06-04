"""Audit-trail use cases (tenant admin)."""

from __future__ import annotations

from medicore.application.common.context import ActorContext
from medicore.application.common.permissions import ensure_can_manage_users
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.repositories._support import AuditFilter, Page, Paging


class ListTenantAudit:
    """Read this clinic's audit trail (admin only), most recent first."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self,
        actor: ActorContext,
        filter: AuditFilter | None = None,
        paging: Paging | None = None,
    ) -> Page[AuditLog]:
        ensure_can_manage_users(actor)  # admin-only, same gate as user management
        return self._uow.audit.list(filter, paging)
