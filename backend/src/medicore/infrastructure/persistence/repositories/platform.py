"""SQLAlchemy platform repositories (superadmin + platform audit). Not tenant-scoped."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.enums import UserStatus
from medicore.domain.shared.identifiers import AuditLogId, PlatformAdminId
from medicore.infrastructure.persistence.models.platform import (
    PlatformAdminModel,
    PlatformAuditLogModel,
)


def _to_admin(row: PlatformAdminModel) -> PlatformAdmin:
    return PlatformAdmin(
        id=PlatformAdminId.parse(row.id),
        name=row.name,
        email=row.email,
        password_hash=row.password_hash,
        status=UserStatus(row.status),
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
    )


def _to_audit(row: PlatformAuditLogModel) -> PlatformAuditLog:
    return PlatformAuditLog(
        id=AuditLogId.parse(row.id),
        actor_id=PlatformAdminId.parse(row.actor_id),
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        metadata=dict(row.metadata_ or {}),
        timestamp=row.timestamp,
    )


class SqlPlatformAdminRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, admin_id: PlatformAdminId) -> PlatformAdmin | None:
        row = self._s.get(PlatformAdminModel, admin_id.value)
        return _to_admin(row) if row else None

    def get_by_email(self, email: str) -> PlatformAdmin | None:
        row = (
            self._s.query(PlatformAdminModel)
            .filter(PlatformAdminModel.email == email.strip().lower())
            .first()
        )
        return _to_admin(row) if row else None

    def save(self, admin: PlatformAdmin) -> None:
        row = self._s.get(PlatformAdminModel, admin.id.value)
        if row is None:
            row = PlatformAdminModel(id=admin.id.value)
            self._s.add(row)
        row.name = admin.name
        row.email = admin.email.strip().lower()
        row.password_hash = admin.password_hash
        row.status = str(admin.status)
        row.last_seen_at = admin.last_seen_at
        row.created_at = admin.created_at


class SqlPlatformAuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def append(self, entry: PlatformAuditLog) -> None:
        self._s.add(
            PlatformAuditLogModel(
                id=entry.id.value,
                actor_id=entry.actor_id.value,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                metadata_=dict(entry.metadata),
                timestamp=entry.timestamp,
            )
        )

    def list(self, limit: int = 100, offset: int = 0) -> list[PlatformAuditLog]:
        rows = (
            self._s.query(PlatformAuditLogModel)
            .order_by(PlatformAuditLogModel.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_to_audit(r) for r in rows]
