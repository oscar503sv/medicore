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
            plan_code="clinica",  # seeded by the subscriptions migration
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


class TestLastFor:
    def _entry_on(self, tenant, actor, entity_id, hour, action="consultation.viewed"):
        return AuditLog(
            id=AuditLogId.new(), tenant_id=tenant, actor_id=actor, action=action,
            entity_type="Consultation", entity_id=entity_id, metadata={"keys": ["full"]},
            timestamp=datetime(2026, 6, 1, hour, 0, tzinfo=UTC),
        )

    def test_returns_the_most_recent_per_entity_action_and_actor(self, session):
        tenant = _tenant(session)
        repo = SqlAuditLogRepository(session, tenant)
        actor, other_actor = UserId.new(), UserId.new()
        repo.append(self._entry_on(tenant, actor, "c1", 9))
        repo.append(self._entry_on(tenant, actor, "c1", 11))
        repo.append(self._entry_on(tenant, actor, "c1", 12, action="consultation.note_updated"))
        repo.append(self._entry_on(tenant, other_actor, "c1", 13))
        repo.append(self._entry_on(tenant, actor, "c2", 14))
        session.flush()

        last = repo.last_for("Consultation", "c1", "consultation.viewed", actor)
        assert last is not None and last.timestamp == datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
        assert repo.last_for("Consultation", "c3", "consultation.viewed", actor) is None

    def test_is_isolated_by_tenant(self, session):
        tenant, other_tenant = _tenant(session), _tenant(session)
        actor = UserId.new()
        SqlAuditLogRepository(session, other_tenant).append(
            self._entry_on(other_tenant, actor, "c1", 9)
        )
        session.flush()
        repo = SqlAuditLogRepository(session, tenant)
        assert repo.last_for("Consultation", "c1", "consultation.viewed", actor) is None

    def test_coalescing_compares_the_database_timestamps(self, session):
        from datetime import timedelta
        from types import SimpleNamespace

        from medicore.application.common.audit import append_coalesced

        tenant = _tenant(session)
        repo = SqlAuditLogRepository(session, tenant)
        uow = SimpleNamespace(audit=repo)
        actor = UserId.new()
        first = self._entry_on(tenant, actor, "c1", 9)
        assert append_coalesced(uow, first, ["full"])
        session.flush()
        soon = self._entry_on(tenant, actor, "c1", 9)
        object.__setattr__(soon, "timestamp", first.timestamp + timedelta(minutes=3))
        assert not append_coalesced(uow, soon, ["full"])
        later = self._entry_on(tenant, actor, "c1", 9)
        object.__setattr__(later, "timestamp", first.timestamp + timedelta(minutes=11))
        assert append_coalesced(uow, later, ["full"])
