"""Integration test: application orders/records round-trip and queries on real PostgreSQL.

Same harness as the other SQL tests — skipped when PostgreSQL is unreachable, rolled back.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.application import (
    ApplicationDraft,
    ApplicationOrder,
    ApplicationRecord,
)
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOrderStatus,
    ApplicationOutcome,
    ApplicationRoute,
    ApplicationSite,
    Role,
)
from medicore.domain.shared.identifiers import ApplicationOrderId, ApplicationRecordId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.mappers._json import (
    application_draft_to_dict,
    dict_to_application_draft,
)
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 6, 5, 15, 0, tzinfo=UTC)


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


def test_orders_and_records_round_trip(session):
    tenant = build_tenant(slug=f"test-apl-{ApplicationOrderId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    nurse = build_user(tenant.id, Role.NURSE, email="nurse@apl.test")
    uow.users.save(nurse)
    ana = build_patient(tenant.id, code="P-00001", first_name="Ana", last_name="Ayala")
    uow.patients.save(ana)
    session.flush()

    ext = ApplicationOrder(
        id=ApplicationOrderId.new(), tenant_id=tenant.id, patient_id=ana.id,
        drug="Ceftriaxona", dose="1 g", route=ApplicationRoute.INTRAMUSCULAR,
        source=ApplicationOrderSource.EXTERNAL, starts_at=datetime(2026, 6, 5, 9, 0),
        created_by_id=nurse.id, doses_total=3, interval_hours=24,
        external_prescriber="Dr. Ramos", external_jvpm="12345", created_at=NOW,
    )
    uow.applications.save_order(ext)
    session.flush()

    def rec(n, at, **kw):
        r = ApplicationRecord(
            id=ApplicationRecordId.new(), tenant_id=tenant.id, order_id=ext.id,
            patient_id=ana.id, dose_number=n, outcome=kw.pop("outcome", ApplicationOutcome.APPLIED),
            recorded_at=at, recorded_by_id=nurse.id, lot="CF-1", lot_expiry=date(2027, 1, 1),
            site=ApplicationSite.LEFT_GLUTEUS, temperature=36.8,
            observe_until=at + timedelta(minutes=30), **kw,
        )
        uow.applications.save_record(r)
        return r

    yesterday = rec(1, NOW - timedelta(days=1))
    yesterday.close_observation(nurse.id, False, None, NOW - timedelta(days=1))
    uow.applications.save_record(yesterday)
    today = rec(2, NOW)
    voided = rec(3, NOW + timedelta(minutes=5))
    voided.void(nurse.id, "Error", NOW)
    uow.applications.save_record(voided)
    ext.refresh({1, 2})
    uow.applications.save_order(ext)
    session.flush()
    session.expunge_all()

    loaded = uow.applications.get_order(ext.id)
    assert loaded.status == ApplicationOrderStatus.IN_PROGRESS
    assert (loaded.route, loaded.source, loaded.external_jvpm) == (
        ApplicationRoute.INTRAMUSCULAR, ApplicationOrderSource.EXTERNAL, "12345"
    )
    assert [o.id for o in uow.applications.list_open_orders()] == [ext.id]
    assert [o.id for o in uow.applications.list_orders_by_patient(ana.id)] == [ext.id]
    records = uow.applications.list_records_by_orders([ext.id])
    assert [r.dose_number for r in records] == [1, 2, 3]
    assert records[0].site == ApplicationSite.LEFT_GLUTEUS and records[0].temperature == 36.8
    assert [r.id for r in uow.applications.list_observing()] == [today.id]
    day = uow.applications.list_records_between(NOW - timedelta(hours=6), NOW + timedelta(hours=6))
    assert [r.id for r in day] == [today.id]  # voided excluded


def test_application_draft_json_round_trip():
    d = ApplicationDraft(drug="Salbutamol", dose="2.5 mg", route=ApplicationRoute.NEBULIZED,
                         doses_total=3, interval_hours=4, observation_minutes=0)
    assert dict_to_application_draft(application_draft_to_dict(d)) == d
