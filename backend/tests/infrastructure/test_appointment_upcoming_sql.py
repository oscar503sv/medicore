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


def _walk_in_setup(session, tag):
    tenant = build_tenant(slug=f"test-walkin-{tag}-{AppointmentId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@walkin.test")
    uow.users.save(doctor)
    patient = build_patient(tenant.id)
    uow.patients.save(patient)
    session.flush()
    return tenant, uow, doctor, patient


def test_walk_in_flag_round_trips_and_defaults_to_false(session):
    tenant, uow, doctor, patient = _walk_in_setup(session, "flag")
    normal = Appointment(
        id=AppointmentId.new(), tenant_id=tenant.id, code="A-0001", patient_id=patient.id,
        doctor_id=doctor.id, location_id=tenant.primary_location.id,
        type=AppointmentType.CONSULT, scheduled_start=datetime(2026, 6, 8, 9, 0),
        duration_minutes=30, reason="Control", created_by_id=doctor.id,
    )
    walk_in = Appointment.walk_in(
        id=AppointmentId.new(), tenant_id=tenant.id, code="A-0002", patient_id=patient.id,
        doctor_id=doctor.id, location_id=tenant.primary_location.id,
        type=AppointmentType.EMERGENCY, reason="Dolor", duration_minutes=30,
        created_by_id=doctor.id, now=datetime(2026, 6, 8, 10, 0, 40),
    )
    uow.appointments.save(normal)
    uow.appointments.save(walk_in)
    session.flush()
    session.expire_all()

    assert uow.appointments.get_by_id(normal.id).is_walk_in is False
    stored = uow.appointments.get_by_id(walk_in.id)
    assert stored.is_walk_in is True
    assert stored.scheduled_start == datetime(2026, 6, 8, 10, 0)


def test_list_upcoming_keeps_todays_waiting_walk_ins_but_not_older_ones(session):
    tenant, uow, doctor, patient = _walk_in_setup(session, "upcoming")

    def walk_in(code, now, status=AppointmentStatus.CONFIRMED):
        a = Appointment.walk_in(
            id=AppointmentId.new(), tenant_id=tenant.id, code=code, patient_id=patient.id,
            doctor_id=doctor.id, location_id=tenant.primary_location.id,
            type=AppointmentType.EMERGENCY, reason="Dolor", duration_minutes=30,
            created_by_id=doctor.id, now=now,
        )
        a.status = status
        uow.appointments.save(a)
        return a

    waiting = walk_in("A-0001", datetime(2026, 6, 5, 17, 50))
    walk_in("A-0002", datetime(2026, 6, 4, 23, 50))  # yesterday
    walk_in("A-0003", datetime(2026, 6, 5, 17, 40), AppointmentStatus.IN_PROGRESS)
    session.flush()

    assert [a.id for a in uow.appointments.list_upcoming(NOW, 10)] == [waiting.id]
