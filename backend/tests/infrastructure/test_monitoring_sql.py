"""Integration test: the monitoring read model and the error store against PostgreSQL
(catalog queries, session kinds, error grouping, lockouts). One outer transaction rolled
back at the end; SKIP when PostgreSQL is unreachable.

The database may hold other data (the demo), so time-based assertions use instants in
2031, which nothing else reaches.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import PlatformAdminId, SessionId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel
from medicore.infrastructure.persistence.repositories.auth_session import (
    SqlAuthSessionRepository,
)
from medicore.infrastructure.persistence.repositories.monitoring import (
    SqlErrorLogRepository,
    SqlMonitoringReadModel,
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

    def record(when, route="/api/v1/patients"):
        log.record(ErrorEvent(
            id=uuid.uuid4(), occurred_at=when, method="GET", route=route, status=500,
            error_type="RuntimeError", location="use_cases/patients.py:10 in execute",
        ))

    record(FUTURE - timedelta(hours=1))
    record(FUTURE - timedelta(hours=2))
    record(FUTURE - timedelta(hours=3), route="/api/v1/records")
    record(FUTURE - timedelta(days=40))

    reads = SqlMonitoringReadModel(session)
    assert reads.errors_since(FUTURE - timedelta(days=1)) == 3
    top, other = reads.error_groups(FUTURE - timedelta(days=1), 10)
    assert (top.route, top.count) == ("/api/v1/patients", 2)
    assert top.last_at == FUTURE - timedelta(hours=1)
    assert other.count == 1
    assert reads.recent_errors(2, 0).items[0].occurred_at == FUTURE - timedelta(hours=1)

    log.purge_before(FUTURE - timedelta(days=30))
    assert reads.errors_since(FUTURE - timedelta(days=50)) == 3
