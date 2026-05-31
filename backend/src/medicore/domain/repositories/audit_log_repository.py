"""AuditLogRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.audit_log import AuditLog


class AuditLogRepository(Protocol):
    def append(self, entry: AuditLog) -> None: ...

    def query(self, **criteria: object) -> list[AuditLog]: ...
