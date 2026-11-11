"""Integration test: patient search, last visits and upcoming count against real PostgreSQL.

Accent folding (translate), phone digit matching (regexp_replace over the JSONB contact) and
the GROUP BY/DISTINCT aggregates only exist in SQL. Same harness as the other SQL tests —
skipped when PostgreSQL is unreachable, everything rolled back.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, PatientStatus, Role
from medicore.domain.repositories._support import PatientFilter
from medicore.domain.shared.identifiers import AppointmentId
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.models.patient import patient_search_sql
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


def test_search_last_visits_and_upcoming_count(session):
    tenant = build_tenant(slug=f"test-psearch-{AppointmentId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@psearch.test")
    uow.users.save(doctor)
    rosa = build_patient(
        tenant.id, code="P-00001", first_name="Rosa", last_name="Álvarez Díaz",
        contact=ContactInfo(phone="+503 7123-4567"),
    )
    ramon = build_patient(tenant.id, code="P-00002", first_name="Ramón", last_name="Núñez")
    gone = build_patient(
        tenant.id, code="P-00003", first_name="Rosa", last_name="Baja",
        status=PatientStatus.INACTIVE,
    )
    for p in (rosa, ramon, gone):
        uow.patients.save(p)
    session.flush()

    def codes(q, f=None):
        return [p.code for p in uow.patients.search(q, None, f).items]

    assert codes("alvarez") == ["P-00001"]
    assert codes("ramon nunez") == ["P-00002"]
    assert codes("NÚÑEZ") == ["P-00002"]
    assert codes("diaz rosa") == ["P-00001"]
    assert codes("71234567") == ["P-00001"]
    assert codes("50%") == []  # LIKE wildcards are literal
    assert codes("rosa") == ["P-00001", "P-00003"]  # ordered by last name
    assert codes("rosa", PatientFilter(status="inactive")) == ["P-00003"]

    def add(patient, start, status):
        uow.appointments.save(
            Appointment(
                id=AppointmentId.new(), tenant_id=tenant.id, code=f"A-{start:%m%d%H}",
                patient_id=patient.id, doctor_id=doctor.id,
                location_id=tenant.primary_location.id, type=AppointmentType.CONSULT,
                scheduled_start=start, duration_minutes=30, reason="Control",
                created_by_id=doctor.id, status=status,
            )
        )

    add(rosa, datetime(2026, 5, 1, 9, 0), AppointmentStatus.COMPLETED)
    add(rosa, datetime(2026, 5, 20, 9, 0), AppointmentStatus.COMPLETED)
    add(rosa, datetime(2026, 5, 28, 9, 0), AppointmentStatus.NO_SHOW)
    add(rosa, datetime(2026, 6, 8, 9, 0), AppointmentStatus.SCHEDULED)
    add(rosa, datetime(2026, 6, 9, 9, 0), AppointmentStatus.CONFIRMED)
    add(ramon, datetime(2026, 6, 5, 17, 0), AppointmentStatus.SCHEDULED)  # before NOW
    session.flush()

    last = uow.appointments.last_visits([rosa.id, ramon.id])
    assert last == {rosa.id: datetime(2026, 5, 20, 9, 0)}
    assert uow.appointments.count_patients_with_upcoming(NOW) == 1


def test_search_query_can_use_the_trigram_indexes(session):
    """The planner only matches an expression index when the query repeats the expression
    exactly; a drift (e.g. constants sent as bound parameters) silently means full scans.
    Checked in two deterministic steps instead of on a plan, which depends on data volume:
    the repository's SQL embeds the shared expressions verbatim, and each of them is
    servable by its index."""
    tenant = build_tenant(slug=f"test-ptrgm-{AppointmentId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()

    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM patients" in statement and "LIKE" in statement:
            statements.append(statement)

    engine = session.connection().engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        uow.patients.search("rosa 71234567")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert statements, "search query not captured"

    exprs = patient_search_sql("patients.")
    for expr in exprs.values():
        assert expr in statements[-1]

    session.execute(text("SET LOCAL enable_seqscan = off"))
    for key, expr in exprs.items():
        plan = "\n".join(
            session.execute(text(f"EXPLAIN SELECT 1 FROM patients WHERE {expr} LIKE '%abc%'"))
            .scalars()
        )
        assert f"ix_patients_search_{key}_trgm" in plan, plan
