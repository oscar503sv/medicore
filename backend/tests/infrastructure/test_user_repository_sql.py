"""Integration test: a user's per-user permission adjustments round-trip through
PostgreSQL (JSONB column). Same harness as the other SQL tests: one outer transaction
rolled back at the end, SKIP when PostgreSQL is unreachable."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.enums import Role
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.repositories.user import SqlUserRepository
from tests.support.builders import build_tenant, build_user


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


def test_permission_adjustments_round_trip(session):
    tenant = build_tenant(f"uperm-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    repo = SqlUserRepository(session, tenant.id)
    user = build_user(tenant.id, Role.NURSE, email="nurse@uperm.test")
    repo.save(user)
    session.flush()
    session.expire_all()
    assert repo.get_by_id(user.id).permission_adjustments.is_empty

    adj = PermissionAdjustments(
        granted=frozenset({"audit.view"}), revoked=frozenset({"patients.view"})
    )
    stored = repo.get_by_id(user.id)
    stored.adjust_permissions(adj)
    repo.save(stored)
    session.flush()
    session.expire_all()
    assert repo.get_by_id(user.id).permission_adjustments == adj
