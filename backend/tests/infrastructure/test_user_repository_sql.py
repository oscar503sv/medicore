"""Integration test: a user's per-user permission adjustments round-trip through
PostgreSQL (JSONB column). Same harness as the other SQL tests: one outer transaction
rolled back at the end, SKIP when PostgreSQL is unreachable."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.enums import Role, UserStatus
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.models.user import UserModel
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


def test_lock_active_admin_ids_returns_only_active_admins_in_id_order(session):
    tenant = build_tenant(f"uadm-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    repo = SqlUserRepository(session, tenant.id)
    admins = [
        build_user(tenant.id, Role.ADMIN, email=f"admin{i}@uadm.test") for i in range(3)
    ]
    suspended = build_user(
        tenant.id, Role.ADMIN, email="gone@uadm.test", status=UserStatus.SUSPENDED
    )
    doctor = build_user(tenant.id, Role.DOCTOR, email="doctor@uadm.test")
    for user in (*admins, suspended, doctor):
        repo.save(user)
    session.flush()

    assert repo.lock_active_admin_ids() == sorted(
        (a.id for a in admins), key=lambda i: i.value
    )


def test_a_concurrent_admin_change_waits_for_the_first_and_sees_its_result(engine):
    slug = f"uconc-{uuid.uuid4().hex[:10]}"
    with engine.begin() as conn:
        setup = Session(bind=conn)
        tenant = build_tenant(slug)
        SqlTenantRepository(setup).save(tenant)
        first = build_user(tenant.id, Role.ADMIN, email="a@uconc.test")
        second = build_user(tenant.id, Role.ADMIN, email="b@uconc.test")
        repo = SqlUserRepository(setup, tenant.id)
        repo.save(first)
        repo.save(second)
        setup.flush()
        setup.close()

    holder = engine.connect()
    waiter = engine.connect()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        holding = holder.begin()
        holder_session = Session(bind=holder, expire_on_commit=False)
        holder_repo = SqlUserRepository(holder_session, tenant.id)
        holder_repo.lock_active_admin_ids()
        demoted = holder_repo.get_by_id(second.id)
        demoted.role = Role.DOCTOR
        holder_repo.save(demoted)
        holder_session.flush()

        def contender() -> list:
            with Session(bind=waiter) as s:
                return SqlUserRepository(s, tenant.id).lock_active_admin_ids()

        future = pool.submit(contender)
        with pytest.raises(FutureTimeout):
            future.result(timeout=0.5)

        holding.commit()
        assert future.result(timeout=5) == [first.id]
    finally:
        pool.shutdown(wait=True)
        holder.close()
        waiter.close()
        with engine.begin() as conn:
            conn.execute(delete(UserModel).where(UserModel.tenant_id == tenant.id.value))
            conn.execute(delete(TenantModel).where(TenantModel.id == tenant.id.value))
