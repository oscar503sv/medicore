"""Integration test: MFA recovery codes against PostgreSQL (rolled back; SKIP without it)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.shared.identifiers import PlatformAdminId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.repositories.platform import (
    SqlPlatformAdminRepository,
    SqlPlatformRecoveryCodeRepository,
)

NOW = datetime(2031, 3, 5, 12, 0, tzinfo=UTC)


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


def _admin(session) -> PlatformAdmin:
    admin = PlatformAdmin(
        id=PlatformAdminId.new(),
        name="Super",
        email=f"{PlatformAdminId.new()}@medicore.test",
        password_hash="x",
    )
    SqlPlatformAdminRepository(session).save(admin)
    session.flush()
    return admin


def test_replace_all_stores_a_fresh_set(session):
    repo = SqlPlatformRecoveryCodeRepository(session)
    admin = _admin(session)
    repo.replace_all(admin.id, ["a" * 64, "b" * 64], NOW)
    assert repo.remaining(admin.id) == 2
    repo.replace_all(admin.id, ["c" * 64], NOW)
    assert repo.remaining(admin.id) == 1
    assert repo.consume(admin.id, "a" * 64, NOW) is False  # old codes are gone


def test_consume_is_single_use(session):
    repo = SqlPlatformRecoveryCodeRepository(session)
    admin = _admin(session)
    repo.replace_all(admin.id, ["a" * 64, "b" * 64], NOW)
    assert repo.consume(admin.id, "a" * 64, NOW) is True
    assert repo.consume(admin.id, "a" * 64, NOW) is False
    assert repo.remaining(admin.id) == 1


def test_consume_unknown_code_or_other_admin_fails(session):
    repo = SqlPlatformRecoveryCodeRepository(session)
    admin, other = _admin(session), _admin(session)
    repo.replace_all(admin.id, ["a" * 64], NOW)
    assert repo.consume(admin.id, "z" * 64, NOW) is False
    assert repo.consume(other.id, "a" * 64, NOW) is False


def test_delete_all_removes_every_code(session):
    repo = SqlPlatformRecoveryCodeRepository(session)
    admin = _admin(session)
    repo.replace_all(admin.id, ["a" * 64], NOW)
    repo.delete_all(admin.id)
    assert repo.remaining(admin.id) == 0


def test_a_hash_cannot_repeat_for_the_same_admin(session):
    repo = SqlPlatformRecoveryCodeRepository(session)
    admin = _admin(session)
    with pytest.raises(IntegrityError):
        repo.replace_all(admin.id, ["a" * 64, "a" * 64], NOW)


def test_mfa_fields_survive_a_round_trip(session):
    repo = SqlPlatformAdminRepository(session)
    admin = _admin(session)
    admin.start_mfa_enrollment("sealed-pending")
    admin.confirm_mfa(NOW, 57)
    repo.save(admin)
    session.flush()
    session.expire_all()
    loaded = repo.get_by_id(admin.id)
    assert loaded is not None
    assert loaded.mfa_enabled and loaded.mfa_secret == "sealed-pending"
    assert loaded.mfa_pending_secret is None
    assert loaded.mfa_last_step == 57 and loaded.mfa_enabled_at == NOW
