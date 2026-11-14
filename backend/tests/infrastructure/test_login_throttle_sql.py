"""Integration tests: SqlLoginThrottleRepository against a real PostgreSQL.

The atomic UPSERT (INSERT … ON CONFLICT … RETURNING) only exists in SQL — the in-memory
fake mirrors the policy but not the statement, so the counting/windowing is verified here
for real. Same harness as the other SQL tests: TEST_DATABASE_URL (or DATABASE_URL from
settings), one outer transaction rolled back at the end, and SKIP when PostgreSQL is
unreachable.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.application.common.login_throttle import ACCOUNT_IP_POLICY, IP_POLICY
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


def _count(repo, identifier):
    return repo._s.execute(
        text("SELECT failed_count FROM login_attempts WHERE identifier = :id"), {"id": identifier}
    ).scalar_one()


def _reserve(repo, identifier=IDENTIFIER, at=NOW, policy=ACCOUNT_IP_POLICY):
    return repo.reserve(identifier, policy, at)


def test_below_threshold_not_locked(repo):
    for _ in range(4):
        reservation = _reserve(repo)
        assert reservation.allowed
    assert reservation.locked_until is None
    assert not reservation.engaged


def test_fifth_attempt_engages_a_one_minute_lock_and_the_sixth_is_rejected(repo):
    for _ in range(4):
        _reserve(repo)
    fifth = _reserve(repo)
    assert fifth.allowed and fifth.engaged
    assert fifth.locked_until == NOW + timedelta(minutes=1)

    sixth = _reserve(repo)
    assert not sixth.allowed
    assert sixth.locked_until == fifth.locked_until
    assert _count(repo, IDENTIFIER) == 5  # a rejection is not counted
    # an expired lock no longer blocks
    assert _reserve(repo, at=NOW + timedelta(seconds=61)).allowed


def test_flat_policy_locks_for_the_whole_period(repo):
    for _ in range(29):
        _reserve(repo, policy=IP_POLICY)
    thirtieth = _reserve(repo, policy=IP_POLICY)
    assert thirtieth.locked_until == NOW + timedelta(minutes=15)


def test_stale_attempts_restart_the_count(repo):
    for _ in range(4):
        _reserve(repo)
    later = NOW + timedelta(minutes=16)
    for _ in range(4):  # window expired: counts 1..4
        assert not _reserve(repo, at=later).engaged
    assert _reserve(repo, at=later).locked_until == later + timedelta(minutes=1)


def test_reset_clears_the_history_and_remembers_the_success(repo):
    for _ in range(5):
        _reserve(repo)
    repo.reset(IDENTIFIER, NOW)

    after = _reserve(repo, at=NOW + timedelta(minutes=2))
    assert after.allowed and after.locked_until is None
    assert after.last_success_at == NOW
    assert _count(repo, IDENTIFIER) == 1


def test_clear_account_forgets_the_account_and_its_pairs_only(repo):
    account = "tenant:t:d_c@x.test"
    pair = f"{account}|203.0.113.9"
    lookalike = "tenant:t:dxc@x.test|203.0.113.9"  # "_" must not act as a wildcard
    shared_ip = "ip:203.0.113.9"
    for identifier in (account, pair, lookalike, shared_ip):
        for _ in range(5):
            _reserve(repo, identifier)
    repo.reset(pair, NOW)  # leaves a last_success_at to keep
    for _ in range(5):
        _reserve(repo, pair)
    ip_before = _count(repo, shared_ip)

    repo.clear_account(account)

    for identifier in (account, pair):
        failed, locked_until = repo._s.execute(
            text("SELECT failed_count, locked_until FROM login_attempts WHERE identifier = :id"),
            {"id": identifier},
        ).one()
        assert (failed, locked_until) == (0, None)
    assert _reserve(repo, pair, at=NOW + timedelta(seconds=1)).last_success_at == NOW
    assert _count(repo, lookalike) == 5
    assert _count(repo, shared_ip) == ip_before


def test_refund_lifts_a_lock_that_falls_below_the_threshold(repo):
    for _ in range(5):
        _reserve(repo)
    repo.refund(IDENTIFIER, ACCOUNT_IP_POLICY)

    assert _count(repo, IDENTIFIER) == 4
    assert _reserve(repo).allowed  # no longer locked


def test_refund_never_goes_below_zero(repo):
    _reserve(repo)
    repo.refund(IDENTIFIER, ACCOUNT_IP_POLICY)
    repo.refund(IDENTIFIER, ACCOUNT_IP_POLICY)
    assert _count(repo, IDENTIFIER) == 0


def test_purge_stale_keeps_recent_locked_and_recently_successful_entries(repo):
    stale, recent, locked, known, forgotten = (
        f"tenant:test-throttle:{n}@example.test" for n in "srlkf"
    )
    old = NOW - timedelta(minutes=30)
    _reserve(repo, stale, old)  # attempted long ago, never locked
    _reserve(repo, recent, NOW - timedelta(minutes=5))  # still inside the window
    _reserve(repo, locked, NOW - timedelta(minutes=16))
    repo._s.execute(
        text("UPDATE login_attempts SET locked_until = :lu WHERE identifier = :id"),
        {"lu": NOW + timedelta(minutes=5), "id": locked},
    )
    for ident, days in ((known, 10), (forgotten, 31)):
        _reserve(repo, ident, old)
        repo._s.execute(
            text("UPDATE login_attempts SET last_success_at = :at WHERE identifier = :id"),
            {"at": NOW - timedelta(days=days), "id": ident},
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
    assert left == {recent, locked, known}


def test_parallel_reservations_never_exceed_the_threshold(engine):
    identifier = f"tenant:test-throttle:{uuid.uuid4().hex}@example.test|203.0.113.1"
    workers = 12
    pool = create_engine(engine.url, pool_size=workers, max_overflow=0)
    barrier = threading.Barrier(workers)
    results: list[bool] = []

    def attempt() -> None:
        with Session(bind=pool) as session:
            barrier.wait(timeout=10)
            allowed = SqlLoginThrottleRepository(session).reserve(
                identifier, ACCOUNT_IP_POLICY, NOW
            ).allowed
        results.append(allowed)

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        with pool.connect() as conn:
            count, locked_until = conn.execute(
                text(
                    "SELECT failed_count, locked_until FROM login_attempts WHERE identifier = :id"
                ),
                {"id": identifier},
            ).one()
        assert len(results) == workers
        assert results.count(True) == ACCOUNT_IP_POLICY.max_attempts
        assert count == ACCOUNT_IP_POLICY.max_attempts
        assert locked_until is not None
    finally:
        with pool.begin() as conn:
            conn.execute(
                text("DELETE FROM login_attempts WHERE identifier = :id"), {"id": identifier}
            )
        pool.dispose()
