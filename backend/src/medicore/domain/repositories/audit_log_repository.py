"""AuditLogRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.repositories._support import AuditFilter, Page, Paging


class AuditLogRepository(Protocol):
    def append(self, entry: AuditLog) -> None: ...

    def query(self, **criteria: object) -> list[AuditLog]: ...

    def list(
        self, filter: AuditFilter | None = None, paging: Paging | None = None
    ) -> Page[AuditLog]: ...
