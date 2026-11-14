"""Integration test: closing every session of a clinic at once, against PostgreSQL.
One outer transaction rolled back at the end; SKIP when PostgreSQL is unreachable."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import PlatformAdminId, SessionId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.repositories.auth_session import (
    SqlAuthSessionRepository,
)
from medicore.infrastructure.persistence.repositories.platform import (
    SqlPlatformAdminRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.repositories.user import SqlUserRepository
from tests.support.builders import build_tenant, build_user

NOW = datetime(2031, 3, 5, 12, 0, tzinfo=UTC)
EARLIER = NOW - timedelta(hours=2)


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


def _clinic_user(session, label: str):
    tenant = build_tenant(f"{label}-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    user = build_user(tenant.id, Role.ADMIN, email=f"admin@{label}.test")
    SqlUserRepository(session, tenant.id).save(user)
    return tenant, user


def test_revoke_all_for_tenant_revokes_only_that_clinic(session):
    tenant_a, user_a = _clinic_user(session, "sa")
    tenant_b, user_b = _clinic_user(session, "sb")
    root = PlatformAdmin(
        id=PlatformAdminId.new(), name="Root", email=f"{uuid.uuid4().hex}@sa.test",
        password_hash="x",
    )
    SqlPlatformAdminRepository(session).save(root)
    sessions = SqlAuthSessionRepository(session)

    def add(user_id, tenant_id, *, scope="tenant", impersonator=None, revoked_at=None):
        created = AuthSession(
            id=SessionId.new(), scope=scope, user_id=user_id, tenant_id=tenant_id,
            created_at=EARLIER, expires_at=NOW + timedelta(hours=1),
            impersonator_id=impersonator, revoked_at=revoked_at,
        )
        sessions.add(created)
        return created.id

    active = add(user_a.id.value, tenant_a.id)
    support = add(user_a.id.value, tenant_a.id, impersonator=root.id.value)
    already = add(user_a.id.value, tenant_a.id, revoked_at=EARLIER)
    other_clinic = add(user_b.id.value, tenant_b.id)
    platform = add(root.id.value, None, scope="platform")
    session.flush()

    sessions.revoke_all_for_tenant(tenant_a.id, NOW)
    session.flush()
    session.expire_all()

    assert sessions.get(active).revoked_at == NOW
    assert sessions.get(support).revoked_at == NOW
    assert sessions.get(already).revoked_at == EARLIER
    assert sessions.get(other_clinic).revoked_at is None
    assert sessions.get(platform).revoked_at is None


def test_touch_updates_last_activity_and_skips_revoked(session):
    root = PlatformAdmin(
        id=PlatformAdminId.new(), name="Root", email=f"{uuid.uuid4().hex}@touch.test",
        password_hash="x",
    )
    SqlPlatformAdminRepository(session).save(root)
    sessions = SqlAuthSessionRepository(session)

    def add(revoked_at=None):
        created = AuthSession(
            id=SessionId.new(), scope="platform", user_id=root.id.value,
            created_at=EARLIER, expires_at=NOW + timedelta(hours=1), revoked_at=revoked_at,
        )
        sessions.add(created)
        return created.id

    live = add()
    revoked = add(revoked_at=EARLIER)
    session.flush()

    sessions.touch(live, NOW)
    sessions.touch(revoked, NOW)
    session.flush()
    session.expire_all()

    assert sessions.get(live).last_activity_at == NOW
    assert sessions.get(revoked).last_activity_at is None
