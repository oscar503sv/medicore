"""System-health read model and the server-error store for the platform console.

PostgreSQL catalog queries (server version, database and table sizes, applied migration)
plus aggregates over the global sign-in, session and error tables.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import case, desc, func, text
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.job_run import JobRun
from medicore.domain.repositories._support import (
    ActiveImpersonation,
    ConnectionStats,
    ConsoleLogin,
    DatabaseStatus,
    ErrorGroup,
    JobSummary,
    LockedLogin,
    LoginPressure,
    Page,
    RequestStatsRow,
    TableSize,
)
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.auth_session import AuthSessionModel
from medicore.infrastructure.persistence.models.error_event import ErrorEventModel, JobRunModel
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel
from medicore.infrastructure.persistence.models.platform import (
    PlatformAdminModel,
    PlatformAuditLogModel,
)
from medicore.infrastructure.persistence.models.request_stats import RequestStatsModel
from medicore.infrastructure.persistence.models.tenant import TenantModel

MAX_LOCKED = 20
CONSOLE_LOGIN_ACTIONS = (
    "auth.platform_login", "auth.platform_login_failed", "auth.platform_login_locked",
    "auth.platform_mfa_failed", "auth.platform_mfa_recovery_used",
)


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
        commit=row.commit,
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
            locked=[self._locked(r) for r in locked],
        )

    def _locked(self, row: LoginAttemptModel) -> LockedLogin:
        # A locked second step is keyed by admin id; show it as that admin's console login.
        prefix = "platform-mfa:"
        if row.identifier.startswith(prefix):
            try:
                admin = self._s.get(PlatformAdminModel, UUID(row.identifier.removeprefix(prefix)))
            except ValueError:
                admin = None
            email = admin.email if admin else row.identifier.removeprefix(prefix)
            return LockedLogin("platform", None, email, row.failed_count, row.locked_until)
        return _locked_login(row.identifier, row.failed_count, row.locked_until)

    def lockouts_since(self, since: datetime) -> int:
        clinic = (
            self._s.query(func.count())
            .select_from(AuditLogModel)
            .filter(AuditLogModel.action == "auth.login_locked", AuditLogModel.timestamp >= since)
            .scalar()
        )
        console = (
            self._s.query(func.count())
            .select_from(PlatformAuditLogModel)
            .filter(
                PlatformAuditLogModel.action == "auth.platform_login_locked",
                PlatformAuditLogModel.timestamp >= since,
            )
            .scalar()
        )
        return clinic + console

    def console_logins(self, limit: int) -> list[ConsoleLogin]:
        log = PlatformAuditLogModel
        rows = (
            self._s.query(log, PlatformAdminModel.name)
            .outerjoin(PlatformAdminModel, PlatformAdminModel.id == log.actor_id)
            .filter(log.action.in_(CONSOLE_LOGIN_ACTIONS))
            .order_by(desc(log.timestamp))
            .limit(limit)
            .all()
        )
        return [
            ConsoleLogin(name, r.action, r.timestamp, r.ip_address, r.user_agent)
            for r, name in rows
        ]

    def connections(self) -> ConnectionStats:
        rows = self._s.execute(
            text(
                "SELECT coalesce(state, 'other'), count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() GROUP BY 1"
            )
        ).all()
        by_state = {state: int(n) for state, n in rows}
        limit = self._s.execute(text("SHOW max_connections")).scalar_one()
        return ConnectionStats(
            total=sum(by_state.values()),
            active=by_state.get("active", 0),
            idle=by_state.get("idle", 0),
            idle_in_transaction=by_state.get("idle in transaction", 0)
            + by_state.get("idle in transaction (aborted)", 0),
            max_connections=int(limit),
        )

    def sessions_by_kind(self, now: datetime) -> dict[str, int]:
        kind = case(
            (AuthSessionModel.impersonator_id.is_not(None), "support"),
            else_=AuthSessionModel.scope,
        )
        rows = (
            self._s.query(kind, func.count())
            .filter(
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
                # Pending second-step challenges are not sessions.
                AuthSessionModel.scope != "mfa",
            )
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
        commits = func.array_agg(aggregate_order_by(e.commit, e.occurred_at))
        rows = (
            self._s.query(e.method, e.route, e.error_type, e.location, func.count(),
                          func.max(e.occurred_at), func.min(e.occurred_at), commits)
            .filter(e.occurred_at >= since)
            .group_by(e.method, e.route, e.error_type, e.location)
            .order_by(desc(func.count()), desc(func.max(e.occurred_at)))
            .limit(limit)
            .all()
        )
        return [
            ErrorGroup(method, route, kind, where, count, last, first, seen[0], seen[-1])
            for method, route, kind, where, count, last, first, seen in rows
        ]

    def errors_per_day(self, since: datetime) -> list[tuple[date, int]]:
        day = func.date(func.timezone("UTC", ErrorEventModel.occurred_at))
        rows = (
            self._s.query(day, func.count())
            .filter(ErrorEventModel.occurred_at >= since)
            .group_by(day)
            .order_by(day)
            .all()
        )
        return [(d, n) for d, n in rows]

    def job_summaries(self) -> list[JobSummary]:
        j = JobRunModel
        latest = (
            self._s.query(j)
            .distinct(j.job)
            .order_by(j.job, desc(j.finished_at))
            .all()
        )
        success = dict(
            self._s.query(j.job, func.max(j.finished_at)).filter(j.ok.is_(True)).group_by(j.job)
        )
        return [
            JobSummary(
                job=r.job, last_started_at=r.started_at, last_finished_at=r.finished_at,
                last_ok=r.ok, last_detail=r.detail, last_success_at=success.get(r.job),
            )
            for r in latest
        ]

    def request_stats_since(self, since: datetime) -> list[RequestStatsRow]:
        return _read_request_stats(self._s, since)

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


def _read_request_stats(session: Session, since: datetime) -> list[RequestStatsRow]:
    rows = session.query(RequestStatsModel).filter(RequestStatsModel.hour >= since).all()
    return [_stats_row(r) for r in rows]


def _stats_row(r: RequestStatsModel) -> RequestStatsRow:
    return RequestStatsRow(
        hour=r.hour, method=r.method, route=r.route, count=r.count,
        client_errors=r.client_errors, server_errors=r.server_errors, total_ms=r.total_ms,
        max_ms=r.max_ms, buckets=tuple(r.buckets),
    )


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
                commit=event.commit,
            )
        )
        self._s.commit()

    def purge_before(self, cutoff: datetime) -> None:
        self._s.query(ErrorEventModel).filter(ErrorEventModel.occurred_at < cutoff).delete(
            synchronize_session=False
        )
        self._s.commit()


class SqlJobLogRepository:
    """Commits each mutation itself: a failed task still leaves its run behind."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def record(self, run: JobRun) -> None:
        self._s.add(
            JobRunModel(
                id=run.id, job=run.job, started_at=run.started_at, finished_at=run.finished_at,
                ok=run.ok, detail=run.detail,
            )
        )
        self._s.commit()

    def purge_before(self, cutoff: datetime) -> None:
        self._s.query(JobRunModel).filter(JobRunModel.finished_at < cutoff).delete(
            synchronize_session=False
        )
        self._s.commit()


class SqlRequestStatsRepository:
    """Upserts add each batch into the stored hour (bucket arrays added element-wise), so any
    number of workers can flush into the same row. Commits on its own."""

    _UPSERT = text(
        """
        INSERT INTO request_stats
            (hour, method, route, count, client_errors, server_errors, total_ms, max_ms, buckets)
        VALUES
            (:hour, :method, :route, :count, :client_errors, :server_errors, :total_ms,
             :max_ms, :buckets)
        ON CONFLICT (hour, method, route) DO UPDATE SET
            count = request_stats.count + EXCLUDED.count,
            client_errors = request_stats.client_errors + EXCLUDED.client_errors,
            server_errors = request_stats.server_errors + EXCLUDED.server_errors,
            total_ms = request_stats.total_ms + EXCLUDED.total_ms,
            max_ms = GREATEST(request_stats.max_ms, EXCLUDED.max_ms),
            buckets = ARRAY(
                SELECT a + b
                FROM unnest(request_stats.buckets, EXCLUDED.buckets) WITH ORDINALITY AS t(a, b, i)
                ORDER BY i
            )
        """
    )

    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, rows: list[RequestStatsRow]) -> None:
        if not rows:
            return
        self._s.execute(
            self._UPSERT,
            [
                {
                    "hour": r.hour, "method": r.method, "route": r.route, "count": r.count,
                    "client_errors": r.client_errors, "server_errors": r.server_errors,
                    "total_ms": r.total_ms, "max_ms": r.max_ms, "buckets": list(r.buckets),
                }
                for r in rows
            ],
        )
        self._s.commit()

    def purge_before(self, cutoff: datetime) -> None:
        self._s.query(RequestStatsModel).filter(RequestStatsModel.hour < cutoff).delete(
            synchronize_session=False
        )
        self._s.commit()

