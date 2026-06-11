"""SQLAlchemy repository for revocable server-side sessions (not tenant-scoped).

Mutations participate in the surrounding UnitOfWork transaction — they do not commit.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.shared.identifiers import SessionId, TenantId
from medicore.infrastructure.persistence.models.auth_session import AuthSessionModel


def _to_entity(row: AuthSessionModel) -> AuthSession:
    return AuthSession(
        id=SessionId(row.id),
        scope=row.scope,
        user_id=row.user_id,
        tenant_id=TenantId(row.tenant_id) if row.tenant_id else None,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
    )


class SqlAuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, session_id: SessionId) -> AuthSession | None:
        row = self._s.get(AuthSessionModel, session_id.value)
        return _to_entity(row) if row else None

    def add(self, session: AuthSession) -> None:
        self._s.add(
            AuthSessionModel(
                id=session.id.value,
                scope=session.scope,
                user_id=session.user_id,
                tenant_id=session.tenant_id.value if session.tenant_id else None,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                ip_address=session.ip_address,
                user_agent=session.user_agent,
            )
        )

    def list_active_for_user(self, user_id: UUID, now: datetime) -> list[AuthSession]:
        rows = (
            self._s.query(AuthSessionModel)
            .filter(
                AuthSessionModel.user_id == user_id,
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
            )
            .order_by(AuthSessionModel.created_at.desc())
            .all()
        )
        return [_to_entity(r) for r in rows]

    def list_active_for_tenant(self, tenant_id: TenantId, now: datetime) -> list[AuthSession]:
        rows = (
            self._s.query(AuthSessionModel)
            .filter(
                AuthSessionModel.tenant_id == tenant_id.value,
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
            )
            .order_by(AuthSessionModel.created_at.desc())
            .all()
        )
        return [_to_entity(r) for r in rows]

    def revoke(self, session_id: SessionId, now: datetime) -> None:
        self._s.query(AuthSessionModel).filter(
            AuthSessionModel.id == session_id.value,
            AuthSessionModel.revoked_at.is_(None),
        ).update({"revoked_at": now})

    def revoke_all_for_user(
        self, user_id: UUID, now: datetime, except_id: SessionId | None = None
    ) -> None:
        query = self._s.query(AuthSessionModel).filter(
            AuthSessionModel.user_id == user_id,
            AuthSessionModel.revoked_at.is_(None),
        )
        if except_id is not None:
            query = query.filter(AuthSessionModel.id != except_id.value)
        query.update({"revoked_at": now})

    def delete_expired_for_user(self, user_id: UUID, now: datetime) -> None:
        self._s.query(AuthSessionModel).filter(
            AuthSessionModel.user_id == user_id,
            AuthSessionModel.expires_at < now,
        ).delete()
