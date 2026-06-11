"""Integration tests: SqlAuditLogRepository filters against a real PostgreSQL.

The in-memory repository covers the contract; these tests verify the actual SQL —
notably the ``startswith`` category filter (LIKE-wildcard escaping was a security fix)
and the inclusive date boundaries.

They use TEST_DATABASE_URL (or DATABASE_URL from settings) and SKIP when PostgreSQL is
unreachable. Everything runs inside one outer transaction that is rolled back, so the
dev database is left untouched — Postgres DDL is transactional, so even ``create_all``
on a fresh database leaves no trace.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.repositories._support import AuditFilter, Paging
from medicore.domain.shared.identifiers import AuditLogId, TenantId, UserId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.repositories.other import SqlAuditLogRepository


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
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    session.flush()
    return tenant_id


def _entry(tenant_id, actor_id, action, *, day=1, entity_type="Patient") -> AuditLog:
    return AuditLog(
        id=AuditLogId.new(),
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(uuid.uuid4()),
        metadata={"subject": "test"},
        timestamp=datetime(2026, 6, day, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def seeded(session):
    """One tenant with a known set of entries, plus a second tenant as isolation noise."""
    tenant = _tenant(session)
    other_tenant = _tenant(session)
    actor_a = UserId.new()
    actor_b = UserId.new()

    repo = SqlAuditLogRepository(session, tenant)
    repo.append(_entry(tenant, actor_a, "patient.created", day=1))
    repo.append(_entry(tenant, actor_a, "patient.archived", day=2))
    # "patients." prefix — must NOT match category "patient" (the trailing dot matters).
    repo.append(_entry(tenant, actor_b, "patients.imported", day=2, entity_type="Import"))
    repo.append(_entry(tenant, actor_b, "appointment.created", day=3, entity_type="Appointment"))

    other_repo = SqlAuditLogRepository(session, other_tenant)
    other_repo.append(_entry(other_tenant, UserId.new(), "patient.created", day=1))
    session.flush()

    return repo, actor_a, actor_b


class TestListFilters:
    def test_filter_by_exact_action(self, seeded):
        repo, *_ = seeded
        page = repo.list(AuditFilter(action="patient.created"))
        assert page.total == 1
        assert page.items[0].action == "patient.created"

    def test_filter_by_entity_type(self, seeded):
        repo, *_ = seeded
        page = repo.list(AuditFilter(entity_type="Appointment"))
        assert [e.action for e in page.items] == ["appointment.created"]

    def test_filter_by_actor(self, seeded):
        repo, actor_a, _ = seeded
        page = repo.list(AuditFilter(actor_id=str(actor_a)))
        assert page.total == 2
        assert all(e.actor_id == actor_a for e in page.items)

    def test_category_matches_prefix_with_dot(self, seeded):
        repo, *_ = seeded
        page = repo.list(AuditFilter(category="patient"))
        # "patients.imported" must stay out: the filter is "patient." not "patient%".
        assert sorted(e.action for e in page.items) == ["patient.archived", "patient.created"]

    def test_category_like_wildcards_are_escaped(self, seeded):
        repo, *_ = seeded
        # With raw LIKE, "pat%" or "%" would match everything; startswith must escape them.
        assert repo.list(AuditFilter(category="pat%")).total == 0
        assert repo.list(AuditFilter(category="%")).total == 0
        assert repo.list(AuditFilter(category="patient_created")).total == 0  # "_" wildcard

    def test_date_bounds_are_inclusive(self, seeded):
        repo, *_ = seeded
        page = repo.list(AuditFilter(date_from="2026-06-02"))
        assert page.total == 3  # days 2, 2 and 3
        page = repo.list(AuditFilter(date_to="2026-06-02"))
        assert page.total == 3  # days 1, 2 and 2 — the date_to day itself counts
        page = repo.list(AuditFilter(date_from="2026-06-03", date_to="2026-06-03"))
        assert [e.action for e in page.items] == ["appointment.created"]

    def test_combined_filters(self, seeded):
        repo, actor_a, _ = seeded
        page = repo.list(
            AuditFilter(category="patient", actor_id=str(actor_a), date_from="2026-06-02")
        )
        assert [e.action for e in page.items] == ["patient.archived"]

    def test_tenant_isolation(self, seeded):
        repo, *_ = seeded
        page = repo.list()
        assert page.total == 4  # the other tenant's entry neither appears nor counts
        assert all(e.action != "patient.created" or e.tenant_id == page.items[0].tenant_id
                   for e in page.items)

    def test_pagination_and_descending_order(self, seeded):
        repo, *_ = seeded
        page = repo.list(paging=Paging(offset=0, limit=2))
        assert page.total == 4
        assert len(page.items) == 2
        assert page.items[0].action == "appointment.created"  # newest first
        rest = repo.list(paging=Paging(offset=2, limit=2))
        assert len(rest.items) == 2
        timestamps = [e.timestamp for e in page.items + rest.items]
        assert timestamps == sorted(timestamps, reverse=True)


class TestQuery:
    def test_query_filters_by_known_attribute(self, seeded):
        repo, *_ = seeded
        entries = repo.query(action="patient.created")
        assert [e.action for e in entries] == ["patient.created"]

    def test_query_ignores_unknown_keys(self, seeded):
        repo, *_ = seeded
        assert len(repo.query(not_a_column="x")) == 4
