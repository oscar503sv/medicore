"""System-health read model and the server-error store for the platform console.

PostgreSQL catalog queries (server version, database and table sizes, applied migration)
plus aggregates over the global sign-in, session and error tables.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, desc, func, text
from sqlalchemy.orm import Session

from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.repositories._support import (
    ActiveImpersonation,
    DatabaseStatus,
    ErrorGroup,
    LockedLogin,
    LoginPressure,
    Page,
    TableSize,
)
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.auth_session import AuthSessionModel
from medicore.infrastructure.persistence.models.error_event import ErrorEventModel
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel
from medicore.infrastructure.persistence.models.platform import PlatformAdminModel
from medicore.infrastructure.persistence.models.tenant import TenantModel

MAX_LOCKED = 20


def _locked_login(identifier: str, failed_count: int, locked_until: datetime) -> LockedLogin:
    # "tenant:{slug}:{email}" or "platform:{email}" (see application.common.login_throttle).
    scope, _, rest = identifier.partition(":")
    slug, email = rest.split(":", 1) if scope == "tenant" and ":" in rest else (None, rest)
    return LockedLogin(scope, slug, email, failed_count, locked_until)


def _event(row: ErrorEventModel) -> ErrorEvent:
    return ErrorEvent(
        id=row.id,
        occurred_at=row.occurred_at,
        method=row.method,
        route=row.route,
        status=row.status,
        error_type=row.error_type,
        location=row.location,
    )


class SqlMonitoringReadModel:
    def __init__(self, session: Session) -> None:
        self._s = session

    def ping(self) -> None:
        self._s.execute(text("SELECT 1")).scalar_one()

    def database(self) -> DatabaseStatus:
        version = self._s.execute(text("SHOW server_version")).scalar_one()
        size = self._s.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        try:
            with self._s.begin_nested():
                revision = self._s.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar_one_or_none()
        except Exception:  # no alembic_version table (a database built without migrations)
            revision = None
        return DatabaseStatus(version=str(version), size_bytes=int(size), revision=revision)

    def largest_tables(self, limit: int) -> list[TableSize]:
        rows = self._s.execute(
            text(
                """
                SELECT c.relname, pg_total_relation_size(c.oid), GREATEST(c.reltuples, 0)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname = current_schema()
                ORDER BY 2 DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).all()
        return [TableSize(name, int(size), int(rows)) for name, size, rows in rows]

    def login_pressure(self, since: datetime, now: datetime) -> LoginPressure:
        failing, attempts = self._s.query(
            func.count(), func.coalesce(func.sum(LoginAttemptModel.failed_count), 0)
        ).filter(LoginAttemptModel.last_failed_at >= since).one()
        locked = (
            self._s.query(LoginAttemptModel)
            .filter(LoginAttemptModel.locked_until > now)
            .order_by(desc(LoginAttemptModel.locked_until))
            .limit(MAX_LOCKED)
            .all()
        )
        return LoginPressure(
            failing_accounts=int(failing),
            failed_attempts=int(attempts),
            locked=[_locked_login(r.identifier, r.failed_count, r.locked_until) for r in locked],
        )

    def lockouts_since(self, since: datetime) -> int:
        return (
            self._s.query(func.count())
            .select_from(AuditLogModel)
            .filter(AuditLogModel.action == "auth.login_locked", AuditLogModel.timestamp >= since)
            .scalar()
        )

    def sessions_by_kind(self, now: datetime) -> dict[str, int]:
        kind = case(
            (AuthSessionModel.impersonator_id.is_not(None), "support"),
            else_=AuthSessionModel.scope,
        )
        rows = (
            self._s.query(kind, func.count())
            .filter(AuthSessionModel.revoked_at.is_(None), AuthSessionModel.expires_at > now)
            .group_by(kind)
            .all()
        )
        return {"tenant": 0, "support": 0, "platform": 0} | {k: n for k, n in rows}

    def active_impersonations(self, now: datetime) -> list[ActiveImpersonation]:
        admin = PlatformAdminModel
        rows = (
            self._s.query(AuthSessionModel, admin.name, TenantModel.legal_name)
            .outerjoin(admin, admin.id == AuthSessionModel.impersonator_id)
            .outerjoin(TenantModel, TenantModel.id == AuthSessionModel.tenant_id)
            .filter(
                AuthSessionModel.impersonator_id.is_not(None),
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
            )
            .order_by(desc(AuthSessionModel.created_at))
            .all()
        )
        return [
            ActiveImpersonation(
                session_id=str(s.id),
                admin_name=admin,
                tenant_id=str(s.tenant_id) if s.tenant_id else None,
                clinic_name=clinic,
                started_at=s.created_at,
                expires_at=s.expires_at,
                ip_address=s.ip_address,
            )
            for s, admin, clinic in rows
        ]

    def errors_since(self, since: datetime) -> int:
        return (
            self._s.query(func.count())
            .select_from(ErrorEventModel)
            .filter(ErrorEventModel.occurred_at >= since)
            .scalar()
        )

    def error_groups(self, since: datetime, limit: int) -> list[ErrorGroup]:
        e = ErrorEventModel
        rows = (
            self._s.query(e.method, e.route, e.error_type, e.location, func.count(),
                          func.max(e.occurred_at))
            .filter(e.occurred_at >= since)
            .group_by(e.method, e.route, e.error_type, e.location)
            .order_by(desc(func.count()), desc(func.max(e.occurred_at)))
            .limit(limit)
            .all()
        )
        return [ErrorGroup(*row) for row in rows]

    def recent_errors(self, limit: int, offset: int) -> Page[ErrorEvent]:
        total = self._s.query(func.count()).select_from(ErrorEventModel).scalar()
        rows = (
            self._s.query(ErrorEventModel)
            .order_by(desc(ErrorEventModel.occurred_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return Page(items=[_event(r) for r in rows], total=total, offset=offset, limit=limit)


class SqlErrorLogRepository:
    """Commits each mutation itself: it runs from the error handler, after the request's
    own transaction has failed."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def record(self, event: ErrorEvent) -> None:
        self._s.add(
            ErrorEventModel(
                id=event.id,
                occurred_at=event.occurred_at,
                method=event.method,
                route=event.route,
                status=event.status,
                error_type=event.error_type,
                location=event.location,
            )
        )
        self._s.commit()

    def purge_before(self, cutoff: datetime) -> None:
        self._s.query(ErrorEventModel).filter(ErrorEventModel.occurred_at < cutoff).delete(
            synchronize_session=False
        )
        self._s.commit()
