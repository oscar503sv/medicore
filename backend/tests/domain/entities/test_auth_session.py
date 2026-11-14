"""Tests for the AuthSession idle-tracking rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.shared.identifiers import SessionId

CREATED = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
IDLE = timedelta(minutes=30)
EVERY = timedelta(seconds=60)


def make_session(last_activity_at: datetime | None = None) -> AuthSession:
    return AuthSession(
        id=SessionId.new(),
        scope="platform",
        user_id=uuid4(),
        created_at=CREATED,
        expires_at=CREATED + timedelta(hours=8),
        last_activity_at=last_activity_at,
    )


def test_idle_since_falls_back_to_creation_when_never_touched():
    assert make_session().idle_since() == CREATED


def test_idle_since_uses_last_activity():
    last = CREATED + timedelta(minutes=10)
    assert make_session(last).idle_since() == last


def test_is_idle_only_once_the_threshold_is_reached():
    session = make_session()
    assert not session.is_idle(CREATED + IDLE - timedelta(seconds=1), IDLE)
    assert session.is_idle(CREATED + IDLE, IDLE)


def test_is_idle_counts_from_last_activity():
    session = make_session(CREATED + timedelta(minutes=20))
    assert not session.is_idle(CREATED + timedelta(minutes=49), IDLE)
    assert session.is_idle(CREATED + timedelta(minutes=50), IDLE)


def test_needs_touch_respects_granularity():
    session = make_session()
    assert not session.needs_touch(CREATED + timedelta(seconds=59), EVERY)
    assert session.needs_touch(CREATED + EVERY, EVERY)


def test_touch_records_activity_and_resets_idle_clock():
    session = make_session()
    now = CREATED + timedelta(minutes=25)
    session.touch(now)
    assert session.last_activity_at == now
    assert not session.is_idle(now + timedelta(minutes=29), IDLE)
