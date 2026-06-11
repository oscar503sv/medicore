"""Active-session use cases: list and remotely revoke server-side sessions.

Three audiences share the same ``sessions`` store:
- a user managing their own sessions (Settings) — no permission required;
- a clinic admin managing any user's sessions (``users.manage``);
- a platform superadmin viewing/closing a clinic's sessions (support console).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.user import User
from medicore.domain.shared.identifiers import AuditLogId, SessionId, TenantId, UserId


@dataclass(frozen=True, slots=True)
class SessionInfoDTO:
    id: SessionId
    user_id: str
    user_name: str | None
    role: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    expires_at: datetime
    current: bool = False


def _info(session: AuthSession, user: User | None = None, current: bool = False) -> SessionInfoDTO:
    return SessionInfoDTO(
        id=session.id,
        user_id=str(session.user_id),
        user_name=user.name if user else None,
        role=str(user.role) if user else None,
        ip_address=session.ip_address,
        user_agent=session.user_agent,
        created_at=session.created_at,
        expires_at=session.expires_at,
        current=current,
    )


class ListMySessions:
    """The actor's own live sessions, the current one flagged so the UI can mark it."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> list[SessionInfoDTO]:
        with self._uow:
            sessions = self._uow.sessions.list_active_for_user(
                actor.user_id.value, self._clock.now()
            )
        return [_info(s, current=s.id == actor.session_id) for s in sessions]


class RevokeMySession:
    """Close one of the actor's own sessions (closing the current one acts as a logout)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, session_id: SessionId) -> None:
        with self._uow:
            session = self._uow.sessions.get(session_id)
            # A foreign session id is indistinguishable from a non-existent one.
            if session is None or session.user_id != actor.user_id.value:
                raise EntityNotFound("Session", session_id)
            self._uow.sessions.revoke(session_id, self._clock.now())
            self._uow.commit()


def _require_tenant_user(uow: UnitOfWork, user_id: UserId) -> User:
    user = uow.users.get_by_id(user_id)
    if user is None:
        raise EntityNotFound("User", user_id)
    return user


class ListUserSessions:
    """A clinic admin lists the live sessions of one of their users."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId) -> list[SessionInfoDTO]:
        ensure_permission(actor, Permission.USERS_MANAGE)
        with self._uow:
            user = _require_tenant_user(self._uow, user_id)
            sessions = self._uow.sessions.list_active_for_user(
                user_id.value, self._clock.now()
            )
        return [_info(s, user=user) for s in sessions]


class RevokeUserSession:
    """A clinic admin closes one session of one of their users (audited)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId, session_id: SessionId) -> None:
        ensure_permission(actor, Permission.USERS_MANAGE)
        with self._uow:
            user = _require_tenant_user(self._uow, user_id)
            session = self._uow.sessions.get(session_id)
            if session is None or session.user_id != user_id.value:
                raise EntityNotFound("Session", session_id)
            now = self._clock.now()
            self._uow.sessions.revoke(session_id, now)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "session.revoked", "User", str(user.id),
                    subject=subject(user.name),
                )
            )
            self._uow.commit()


class RevokeAllUserSessions:
    """A clinic admin closes every session of one of their users (audited)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId) -> None:
        ensure_permission(actor, Permission.USERS_MANAGE)
        with self._uow:
            user = _require_tenant_user(self._uow, user_id)
            now = self._clock.now()
            self._uow.sessions.revoke_all_for_user(user_id.value, now)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "session.revoked", "User", str(user.id),
                    subject=subject(user.name), all_sessions=True,
                )
            )
            self._uow.commit()


class ListTenantSessions:
    """A platform superadmin lists every live session of a clinic, with user names."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, actor: PlatformActorContext, tenant_id: TenantId) -> list[SessionInfoDTO]:
        with self._factory.for_tenant(tenant_id) as uow:
            sessions = uow.sessions.list_active_for_tenant(tenant_id, self._clock.now())
            users = {s.user_id: uow.users.get_by_id(UserId(s.user_id)) for s in sessions}
        return [_info(s, user=users.get(s.user_id)) for s in sessions]


class RevokeTenantSession:
    """A platform superadmin closes one session inside a clinic (platform-audited)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, session_id: SessionId
    ) -> None:
        with self._factory.for_tenant(tenant_id) as uow:
            session = uow.sessions.get(session_id)
            if session is None or session.tenant_id != tenant_id:
                raise EntityNotFound("Session", session_id)
            now = self._clock.now()
            uow.sessions.revoke(session_id, now)
            uow.platform_audit.append(
                PlatformAuditLog(
                    id=AuditLogId.new(),
                    actor_id=actor.admin_id,
                    action="session.revoked",
                    entity_type="User",
                    entity_id=str(session.user_id),
                    timestamp=now,
                    tenant_id=tenant_id,
                    ip_address=actor.ip_address,
                    user_agent=actor.user_agent,
                )
            )
            uow.commit()
