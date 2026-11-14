"""Integration test: the clinic-row lock that serializes quota checks (PostgreSQL).

Uses real concurrent connections, so committed rows are created and removed explicitly;
SKIP when PostgreSQL is unreachable.
"""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.enums import Role
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
def tenant(engine):
    tenant = build_tenant(f"tlock-{uuid.uuid4().hex[:10]}")
    with engine.begin() as conn:
        setup = Session(bind=conn)
        SqlTenantRepository(setup).save(tenant)
        setup.flush()
        setup.close()
    yield tenant
    with engine.begin() as conn:
        conn.execute(delete(UserModel).where(UserModel.tenant_id == tenant.id.value))
        conn.execute(delete(TenantModel).where(TenantModel.id == tenant.id.value))


def test_a_second_quota_check_waits_for_the_first(engine, tenant):
    holder = engine.connect()
    waiter = engine.connect()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        holding = holder.begin()
        holder_session = Session(bind=holder, expire_on_commit=False)
        SqlTenantRepository(holder_session).lock(tenant.id)

        def contender() -> None:
            with Session(bind=waiter) as session:
                SqlTenantRepository(session).lock(tenant.id)

        future = pool.submit(contender)
        with pytest.raises(FutureTimeout):
            future.result(timeout=0.5)

        holding.commit()
        future.result(timeout=5)
    finally:
        pool.shutdown(wait=True)
        holder.close()
        waiter.close()


def test_lock_does_not_block_inserts_referencing_the_clinic(engine, tenant):
    holder = engine.connect()
    writer = engine.connect()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        holding = holder.begin()
        holder_session = Session(bind=holder, expire_on_commit=False)
        SqlTenantRepository(holder_session).lock(tenant.id)

        def insert_user() -> None:
            with Session(bind=writer) as session:
                user = build_user(tenant.id, Role.NURSE, email="nurse@tlock.test")
                SqlUserRepository(session, tenant.id).save(user)
                session.commit()

        # A plain FOR UPDATE would hold this insert back (its FK check takes FOR KEY SHARE).
        pool.submit(insert_user).result(timeout=5)
        holding.rollback()
    finally:
        pool.shutdown(wait=True)
        holder.close()
        writer.close()
