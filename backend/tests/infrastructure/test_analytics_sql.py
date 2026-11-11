"""Integration tests: the practice-metrics read model against PostgreSQL (one outer
transaction rolled back at the end; SKIP when PostgreSQL is unreachable)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role
from medicore.domain.shared.identifiers import AppointmentId, TenantId
from medicore.domain.value_objects.fee import Charge, fee
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user


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


def test_facts_first_visits_and_counts(session):
    tenant = build_tenant(slug=f"test-analytics-{TenantId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@analytics.test")
    other = build_user(tenant.id, Role.DOCTOR, email="otro@analytics.test")
    for u in (doctor, other):
        uow.users.save(u)
    ana = build_patient(tenant.id, code="P-00001")
    uow.patients.save(ana)
    session.flush()

    def book(start, status, who, charged):
        uow.appointments.save(Appointment(
            id=AppointmentId.new(), tenant_id=tenant.id, code="A-1", patient_id=ana.id,
            doctor_id=who.id, location_id=tenant.primary_location.id,
            type=AppointmentType.CONSULT, scheduled_start=start, duration_minutes=30,
            reason="Control", created_by_id=who.id, status=status,
            charge=Charge.at_list_price(fee(charged)),
        ))

    book(datetime(2026, 4, 2, 9), AppointmentStatus.COMPLETED, other, 40)
    book(datetime(2026, 5, 4, 9), AppointmentStatus.COMPLETED, doctor, 30)
    book(datetime(2026, 5, 5, 9), AppointmentStatus.NO_SHOW, doctor, 30)
    session.flush()

    facts = uow.analytics.appointment_facts(datetime(2026, 5, 1), datetime(2026, 6, 1))
    assert sorted((f.status, f.charged) for f in facts) == [
        ("completed", Decimal("30.00")), ("no_show", Decimal("30.00"))]
    assert facts[0].patient_id == str(ana.id) and facts[0].insurer_id is None
    assert uow.analytics.appointment_facts(
        datetime(2026, 5, 1), datetime(2026, 6, 1), other.id) == []

    assert uow.analytics.first_visits([ana.id]) == {ana.id: datetime(2026, 4, 2, 9)}
    assert uow.analytics.first_visits([ana.id], doctor.id) == {ana.id: datetime(2026, 5, 4, 9)}
    assert uow.analytics.first_visits([]) == {}

    since, until = datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)
    assert uow.analytics.procedure_facts(since, until) == []
    assert uow.analytics.vaccinations_recorded(date(2026, 5, 1), date(2026, 5, 31)) == 0
    assert uow.analytics.applications_recorded(since, until, doctor.id) == 0
