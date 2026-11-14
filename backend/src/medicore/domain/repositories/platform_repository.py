"""Platform-level repository ports (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.shared.identifiers import PlatformAdminId


class PlatformAdminRepository(Protocol):
    """Superadmin accounts — global, not tenant-scoped."""

    def get_by_id(self, admin_id: PlatformAdminId) -> PlatformAdmin | None: ...

    def get_by_email(self, email: str) -> PlatformAdmin | None: ...

    def save(self, admin: PlatformAdmin) -> None: ...


class PlatformAuditLogRepository(Protocol):
    """Append-only platform action trail — global, not tenant-scoped."""

    def append(self, entry: PlatformAuditLog) -> None: ...

    def list(self, limit: int = 100, offset: int = 0) -> list[PlatformAuditLog]: ...


class PlatformRecoveryCodeRepository(Protocol):
    """Single-use MFA recovery codes of superadmins, stored as hashes — global."""

    def replace_all(self, admin_id: PlatformAdminId, code_hashes: list[str], now: datetime) -> None:
        """Drop every code of the admin (used or not) and store the new set."""
        ...

    def consume(self, admin_id: PlatformAdminId, code_hash: str, now: datetime) -> bool:
        """Mark an unused code as used. Atomic: of two concurrent attempts only one wins."""
        ...

    def remaining(self, admin_id: PlatformAdminId) -> int: ...

    def delete_all(self, admin_id: PlatformAdminId) -> None: ...
