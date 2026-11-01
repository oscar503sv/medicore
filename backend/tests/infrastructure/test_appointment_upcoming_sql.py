"""Integration test: SqlAppointmentRepository.list_upcoming against a real PostgreSQL.

Checks the status filter, the cut-off, ordering, limit and doctor scope in SQL. Same harness
as the other SQL tests — skipped when PostgreSQL is unreachable, everything rolled back.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role
from medicore.domain.shared.identifiers import AppointmentId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 6, 5, 18, 0)


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


def test_list_upcoming_filters_orders_limits_and_scopes(session):
    tenant = build_tenant(slug=f"test-upcoming-{AppointmentId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@upcoming.test")
    other = build_user(tenant.id, Role.DOCTOR, email="other@upcoming.test")
    reception = build_user(tenant.id, Role.RECEPTIONIST, email="rec@upcoming.test")
    for u in (doctor, other, reception):
        uow.users.save(u)
    patient = build_patient(tenant.id)
    uow.patients.save(patient)
    session.flush()

    def add(who, start, status=AppointmentStatus.SCHEDULED):
        a = Appointment(
            id=AppointmentId.new(), tenant_id=tenant.id, code=f"A-{start:%d%H%M}{who.email[0]}",
            patient_id=patient.id, doctor_id=who.id,
            location_id=tenant.primary_location.id, type=AppointmentType.CONSULT,
            scheduled_start=start, duration_minutes=30, reason="Control",
            created_by_id=reception.id, status=status,
        )
        uow.appointments.save(a)
        return a

    add(doctor, datetime(2026, 6, 5, 17, 30))  # before the cut-off
    tue = add(doctor, datetime(2026, 6, 9, 10, 0), AppointmentStatus.CONFIRMED)
    mon = add(doctor, datetime(2026, 6, 8, 9, 0))
    add(doctor, datetime(2026, 6, 8, 9, 30), AppointmentStatus.CANCELLED)
    theirs = add(other, datetime(2026, 6, 8, 8, 0))
    session.flush()

    repo = uow.appointments
    assert [a.id for a in repo.list_upcoming(NOW, 10)] == [theirs.id, mon.id, tue.id]
    assert [a.id for a in repo.list_upcoming(NOW, 10, doctor.id)] == [mon.id, tue.id]
    assert [a.id for a in repo.list_upcoming(NOW, 1)] == [theirs.id]
