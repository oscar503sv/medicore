"""Integration tests: SqlNotificationRepository against a real PostgreSQL.

Covers what the in-memory repository cannot: the JSONB round-trip, the bulk UPDATE/DELETE
statements and tenant/user scoping in SQL. Same harness as the audit SQL tests — skipped
when PostgreSQL is unreachable, everything rolled back afterwards.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.notification import Notification
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import NotificationId, TenantId, UserId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.repositories.other import SqlNotificationRepository

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


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
    Base.metadata.create_all(bind=connection)  # no-op on an already-migrated database
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    connection.close()


def _tenant(session) -> TenantId:
    tenant_id = TenantId.new()
    session.add(
        TenantModel(
            id=tenant_id.value,
            legal_name="Clínica Test SL",
            tax_id="B00000000",
            slug=f"test-{uuid.uuid4().hex[:12]}",
            created_at=NOW,
        )
    )
    session.flush()
    return tenant_id


def _add(repo, tenant_id, user_id, *, minutes_ago=0, read_at=None, data=None) -> Notification:
    n = Notification(
        id=NotificationId.new(),
        tenant_id=tenant_id,
        user_id=user_id,
        type="appointment.created",
        data=data or {"appointment_code": f"A-{minutes_ago}"},
        read_at=read_at,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )
    repo.save(n)
    return n


def test_round_trips_data_and_lists_newest_first(session):
    tid = _tenant(session)
    repo = SqlNotificationRepository(session, tid)
    me, other = UserId.new(), UserId.new()
    old = _add(repo, tid, me, minutes_ago=20, data={"patient_name": "Lucía Álvarez · ñ"})
    new = _add(repo, tid, me, minutes_ago=10)
    _add(repo, tid, other, minutes_ago=5)
    session.flush()

    listed = repo.list_by_user(me)
    assert [n.id for n in listed] == [new.id, old.id]
    assert listed[1].data == {"patient_name": "Lucía Álvarez · ñ"}
    assert [n.id for n in repo.list_by_user(me, paging=Paging(offset=1, limit=1))] == [old.id]
    assert repo.get_by_id(old.id).data == old.data


def test_other_tenant_is_invisible(session):
    tid, foreign_tid = _tenant(session), _tenant(session)
    me = UserId.new()
    foreign = _add(SqlNotificationRepository(session, foreign_tid), foreign_tid, me)
    session.flush()

    repo = SqlNotificationRepository(session, tid)
    assert repo.list_by_user(me) == []
    assert repo.get_by_id(foreign.id) is None
    assert repo.count_unread(me) == 0
    assert repo.mark_all_read(me, NOW) == 0


def test_unread_count_and_mark_all_read(session):
    tid = _tenant(session)
    repo = SqlNotificationRepository(session, tid)
    me, other = UserId.new(), UserId.new()
    _add(repo, tid, me, minutes_ago=2)
    _add(repo, tid, me, minutes_ago=1)
    _add(repo, tid, me, read_at=NOW - timedelta(days=1))
    _add(repo, tid, other)
    session.flush()

    assert repo.count_unread(me) == 2
    assert repo.mark_all_read(me, NOW) == 2
    session.expire_all()
    assert repo.count_unread(me) == 0
    assert repo.count_unread(other) == 1
    assert repo.list_by_user(me, unread_only=True) == []


def test_delete_read_before_keeps_unread_and_recent(session):
    tid = _tenant(session)
    repo = SqlNotificationRepository(session, tid)
    me, other = UserId.new(), UserId.new()
    _add(repo, tid, me, read_at=NOW - timedelta(days=91))
    recent = _add(repo, tid, me, read_at=NOW - timedelta(days=10))
    unread = _add(repo, tid, me)
    theirs = _add(repo, tid, other, read_at=NOW - timedelta(days=91))
    session.flush()

    assert repo.delete_read_before(me, NOW - timedelta(days=90)) == 1
    session.expire_all()
    assert {n.id for n in repo.list_by_user(me)} == {recent.id, unread.id}
    assert repo.get_by_id(theirs.id) is not None
