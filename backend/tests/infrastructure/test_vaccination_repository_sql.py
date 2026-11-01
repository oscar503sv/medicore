"""Integration test: vaccination records round-trip and queries against real PostgreSQL.

Same harness as the other SQL tests — skipped when PostgreSQL is unreachable, rolled back.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    InjectionSite,
    Role,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.shared.identifiers import VaccinationRecordId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 6, 5, 18, 0)
DAY = date(2026, 6, 5)


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


def test_records_round_trip_and_queries(session):
    tenant = build_tenant(slug=f"test-vax-{VaccinationRecordId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    nurse = build_user(tenant.id, Role.NURSE, email="nurse@vax.test")
    uow.users.save(nurse)
    ana = build_patient(tenant.id, code="P-00001", first_name="Ana", last_name="Ayala")
    beto = build_patient(tenant.id, code="P-00002", first_name="Beto", last_name="Cruz")
    for p in (ana, beto):
        uow.patients.save(p)
    session.flush()

    def rec(patient, on, *, code="TD", source=VaccinationSource.CLINIC,
            outcome=VaccinationOutcome.ADMINISTERED, lot="L-1"):
        r = VaccinationRecord(
            id=VaccinationRecordId.new(), tenant_id=tenant.id, patient_id=patient.id,
            vaccine_code=code, dose_key="TD-1" if code == "TD" else None, outcome=outcome,
            occurred_on=on, source=source, recorded_by_id=nurse.id,
            lot=lot if outcome == VaccinationOutcome.ADMINISTERED else None,
            route=VaccineRoute.INTRAMUSCULAR, site=InjectionSite.LEFT_ARM,
            notes="  sin reacción ", created_at=NOW,
        )
        uow.vaccinations.save(r)
        return r

    old = rec(ana, date(2016, 3, 1), source=VaccinationSource.EXTERNAL, lot=None)
    today_here = rec(ana, DAY)
    rec(beto, DAY, outcome=VaccinationOutcome.REFUSED)
    rec(beto, DAY, code="INFLU", source=VaccinationSource.EXTERNAL, lot=None)
    voided = rec(beto, DAY, code="INFLU")
    voided.void(nurse.id, "Paciente equivocado", NOW)
    uow.vaccinations.save(voided)
    session.flush()
    session.expunge_all()

    loaded = uow.vaccinations.get_by_id(today_here.id)
    assert loaded is not None
    assert (loaded.route, loaded.site, loaded.notes) == (
        VaccineRoute.INTRAMUSCULAR, InjectionSite.LEFT_ARM, "sin reacción"
    )
    assert [r.id for r in uow.vaccinations.list_by_patient(ana.id)] == [today_here.id, old.id]
    reloaded = uow.vaccinations.get_by_id(voided.id)
    assert reloaded.is_voided and reloaded.void_reason == "Paciente equivocado"

    active = uow.vaccinations.list_active_by_patients([ana.id, beto.id])
    assert voided.id not in {r.id for r in active} and len(active) == 4
    # Only doses actually given here today (not refused, external or voided).
    assert [r.id for r in uow.vaccinations.list_administered_on(DAY)] == [today_here.id]
