"""Integration tests: SqlLoginThrottleRepository against a real PostgreSQL.

The atomic UPSERT (INSERT … ON CONFLICT … RETURNING) only exists in SQL — the in-memory
fake mirrors the policy but not the statement, so the counting/windowing is verified here
for real. Same harness as the other SQL tests: TEST_DATABASE_URL (or DATABASE_URL from
settings), one outer transaction rolled back at the end, and SKIP when PostgreSQL is
unreachable.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.repositories.login_throttle import (
    SqlLoginThrottleRepository,
)

NOW = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)
IDENTIFIER = "tenant:test-throttle:doc@example.test"


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
def repo(engine):
    connection = engine.connect()
    trans = connection.begin()
    Base.metadata.create_all(bind=connection)  # no-op on an already-migrated database
    session = Session(bind=connection, expire_on_commit=False)

    yield SqlLoginThrottleRepository(session)
    session.close()
    trans.rollback()
    connection.close()


def test_below_threshold_not_locked(repo):
    for _ in range(4):
        locked = repo.record_failure(IDENTIFIER, NOW)
    assert locked is None
    assert repo.locked_until(IDENTIFIER, NOW) is None


def test_fifth_failure_locks_for_one_minute(repo):
    for _ in range(5):
        locked = repo.record_failure(IDENTIFIER, NOW)
    assert locked == NOW + timedelta(minutes=1)
    assert repo.locked_until(IDENTIFIER, NOW) == locked
    # an expired lock no longer blocks
    assert repo.locked_until(IDENTIFIER, NOW + timedelta(seconds=61)) is None


def test_backoff_caps_at_fifteen_minutes(repo):
    locked = None
    for _ in range(10):
        locked = repo.record_failure(IDENTIFIER, NOW)
    assert locked == NOW + timedelta(minutes=15)


def test_stale_failures_restart_the_count(repo):
    for _ in range(4):
        repo.record_failure(IDENTIFIER, NOW)
    later = NOW + timedelta(minutes=16)
    assert repo.record_failure(IDENTIFIER, later) is None  # window expired → count = 1
    for _ in range(3):
        assert repo.record_failure(IDENTIFIER, later) is None  # counts 2..4
    assert repo.record_failure(IDENTIFIER, later) == later + timedelta(minutes=1)


def test_reset_clears_the_history(repo):
    for _ in range(5):
        repo.record_failure(IDENTIFIER, NOW)
    repo.reset(IDENTIFIER)
    assert repo.locked_until(IDENTIFIER, NOW) is None
    assert repo.record_failure(IDENTIFIER, NOW) is None  # back to count = 1


def test_purge_stale_keeps_recent_and_locked_entries(repo):
    stale, recent, locked = (f"tenant:test-throttle:{n}@example.test" for n in "srl")
    old = NOW - timedelta(minutes=30)
    repo.record_failure(stale, old)  # failed long ago, never locked
    repo.record_failure(recent, NOW - timedelta(minutes=5))  # still inside the window
    for _ in range(9):  # 9th failure → 15-minute lockout, still active at NOW
        repo.record_failure(locked, NOW - timedelta(minutes=16))
    repo._s.execute(
        text("UPDATE login_attempts SET locked_until = :lu WHERE identifier = :id"),
        {"lu": NOW + timedelta(minutes=5), "id": locked},
    )

    repo.purge_stale(NOW)

    left = set(
        repo._s.execute(
            text(
                "SELECT identifier FROM login_attempts"
                " WHERE identifier LIKE 'tenant:test-throttle:%'"
            )
        ).scalars()
    )
    assert left == {recent, locked}
