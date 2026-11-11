"""Integration test: the monitoring read model and the error store against PostgreSQL
(catalog queries, session kinds, error grouping, lockouts). One outer transaction rolled
back at the end; SKIP when PostgreSQL is unreachable.

The database may hold other data (the demo), so time-based assertions use instants in
2031, which nothing else reaches.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.job_run import JobRun
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.enums import Role
from medicore.domain.repositories._support import RequestStatsRow
from medicore.domain.shared.identifiers import AuditLogId, PlatformAdminId, SessionId
from medicore.domain.value_objects.latency_histogram import LatencyHistogram
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel
from medicore.infrastructure.persistence.models.platform import PlatformAuditLogModel
from medicore.infrastructure.persistence.repositories.auth_session import (
    SqlAuthSessionRepository,
)
from medicore.infrastructure.persistence.repositories.monitoring import (
    SqlErrorLogRepository,
    SqlJobLogRepository,
    SqlMonitoringReadModel,
    SqlRequestStatsRepository,
)
from medicore.infrastructure.persistence.repositories.platform import (
    SqlPlatformAdminRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.repositories.user import SqlUserRepository
from tests.support.builders import build_tenant, build_user

FUTURE = datetime(2031, 3, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("PostgreSQL not available")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    connection.close()


def test_database_facts(session):
    reads = SqlMonitoringReadModel(session)
    reads.ping()
    db = reads.database()
    assert db.version and db.size_bytes > 0
    assert db.revision  # the test database is migrated
    tables = reads.largest_tables(5)
    assert 0 < len(tables) <= 5
    assert tables == sorted(tables, key=lambda t: t.size_bytes, reverse=True)


def test_sessions_by_kind_and_open_support_access(session):
    tenant = build_tenant(f"mon-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    admin_user = build_user(tenant.id, Role.ADMIN, email="admin@mon.test")
    SqlUserRepository(session, tenant.id).save(admin_user)
    root = PlatformAdmin(
        id=PlatformAdminId.new(), name="Root Mon", email=f"{uuid.uuid4().hex}@mon.test",
        password_hash="x",
    )
    SqlPlatformAdminRepository(session).save(root)
    sessions = SqlAuthSessionRepository(session)

    def add(impersonator=None, expires=FUTURE + timedelta(hours=1)):
        sessions.add(AuthSession(
            id=SessionId.new(), scope="tenant", user_id=admin_user.id.value,
            created_at=FUTURE - timedelta(minutes=5), expires_at=expires, tenant_id=tenant.id,
            impersonator_id=impersonator,
        ))

    add()
    add(impersonator=root.id.value)
    add(expires=FUTURE - timedelta(minutes=1))
    session.flush()

    reads = SqlMonitoringReadModel(session)
    assert reads.sessions_by_kind(FUTURE) == {"tenant": 1, "support": 1, "platform": 0}
    [support] = reads.active_impersonations(FUTURE)
    assert (support.admin_name, support.clinic_name) == ("Root Mon", tenant.legal_name)


def test_login_pressure(session):
    session.add_all([
        LoginAttemptModel(identifier="tenant:mon-x:ana@mon.test", failed_count=6,
                          last_failed_at=FUTURE, locked_until=FUTURE + timedelta(minutes=2)),
        LoginAttemptModel(identifier="platform:root@mon.test", failed_count=2,
                          last_failed_at=FUTURE - timedelta(hours=1)),
    ])
    session.flush()
    pressure = SqlMonitoringReadModel(session).login_pressure(FUTURE - timedelta(hours=2), FUTURE)
    assert (pressure.failing_accounts, pressure.failed_attempts) == (2, 8)
    [locked] = pressure.locked
    assert (locked.scope, locked.clinic_slug, locked.email) == ("tenant", "mon-x", "ana@mon.test")


def test_error_store_groups_pages_and_purges(session):
    log = SqlErrorLogRepository(session)

    def record(when, route="/api/v1/patients", commit=None):
        log.record(ErrorEvent(
            id=uuid.uuid4(), occurred_at=when, method="GET", route=route, status=500,
            error_type="RuntimeError", location="use_cases/patients.py:10 in execute",
            commit=commit,
        ))

    record(FUTURE - timedelta(hours=1), commit="new2222")
    record(FUTURE - timedelta(hours=2), commit="old1111")
    record(FUTURE - timedelta(hours=3), route="/api/v1/records")
    record(FUTURE - timedelta(days=40))

    reads = SqlMonitoringReadModel(session)
    assert reads.errors_since(FUTURE - timedelta(days=1)) == 3
    top, other = reads.error_groups(FUTURE - timedelta(days=1), 10)
    assert (top.route, top.count) == ("/api/v1/patients", 2)
    assert top.last_at == FUTURE - timedelta(hours=1)
    assert (top.first_commit, top.last_commit) == ("old1111", "new2222")
    assert top.first_at == FUTURE - timedelta(hours=2)
    assert other.count == 1
    assert reads.recent_errors(1, 0).items[0].commit == "new2222"
    assert reads.errors_per_day(FUTURE - timedelta(days=2)) == [(date(2031, 3, 5), 3)]
    assert reads.recent_errors(2, 0).items[0].occurred_at == FUTURE - timedelta(hours=1)

    log.purge_before(FUTURE - timedelta(days=30))
    assert reads.errors_since(FUTURE - timedelta(days=50)) == 3


def test_connections(session):
    stats = SqlMonitoringReadModel(session).connections()
    assert stats.total >= 1 and stats.active >= 1  # this very query
    assert stats.max_connections > 0


def test_console_logins_and_lockouts(session):
    root = PlatformAdmin(
        id=PlatformAdminId.new(), name="Root Logins", email=f"{uuid.uuid4().hex}@mon.test",
        password_hash="x",
    )
    SqlPlatformAdminRepository(session).save(root)
    session.flush()
    for minutes, action in ((3, "auth.platform_login_failed"), (2, "auth.platform_login_locked"),
                            (1, "auth.platform_login")):
        session.add(PlatformAuditLogModel(
            id=AuditLogId.new().value, actor_id=root.id.value, action=action,
            entity_type="PlatformAdmin", entity_id=str(root.id), metadata_={},
            timestamp=FUTURE - timedelta(minutes=minutes), ip_address="10.0.0.9",
        ))
    session.flush()
    reads = SqlMonitoringReadModel(session)
    latest = reads.console_logins(3)
    assert [c.action for c in latest] == [
        "auth.platform_login", "auth.platform_login_locked", "auth.platform_login_failed"
    ]
    assert latest[0].admin_name == "Root Logins"
    assert reads.lockouts_since(FUTURE - timedelta(hours=1)) == 1


def test_job_summaries(session):
    log = SqlJobLogRepository(session)
    job = f"zz-job-{uuid.uuid4().hex[:6]}"
    for hours, ok in ((5, True), (3, True), (1, False)):
        log.record(JobRun(
            id=uuid.uuid4(), job=job, started_at=FUTURE - timedelta(hours=hours, minutes=1),
            finished_at=FUTURE - timedelta(hours=hours), ok=ok, detail="x",
        ))
    [summary] = [s for s in SqlMonitoringReadModel(session).job_summaries() if s.job == job]
    assert summary.last_ok is False
    assert summary.last_finished_at == FUTURE - timedelta(hours=1)
    assert summary.last_success_at == FUTURE - timedelta(hours=3)


def test_request_stats_upsert_sums_batches(session):
    store = SqlRequestStatsRepository(session)
    route = f"/api/v1/zz-{uuid.uuid4().hex[:6]}"

    def row(*durations, server=0):
        return RequestStatsRow(
            hour=FUTURE, method="GET", route=route, count=len(durations), client_errors=0,
            server_errors=server, total_ms=float(sum(durations)), max_ms=float(max(durations)),
            buckets=LatencyHistogram.of(*durations).counts,
        )

    store.add([row(20, 40)])
    store.add([row(6000, server=1)])  # a second worker flushing into the same hour

    [stored] = [
        r for r in SqlMonitoringReadModel(session).request_stats_since(FUTURE)
        if r.route == route
    ]
    assert (stored.count, stored.server_errors, stored.max_ms) == (3, 1, 6000)
    assert stored.total_ms == 6060
    assert stored.buckets == LatencyHistogram.of(20, 40, 6000).counts

    store.purge_before(FUTURE + timedelta(hours=1))
    assert not [
        r for r in SqlMonitoringReadModel(session).request_stats_since(FUTURE)
        if r.route == route
    ]
