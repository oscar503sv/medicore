"""Integration test: procedure catalog and procedures round-trip on real PostgreSQL.

Same harness as the other SQL tests — skipped when PostgreSQL is unreachable, rolled back.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.procedure import (
    Procedure,
    ProcedureDraft,
    ProcedureProgress,
    ProcedureType,
)
from medicore.domain.enums import ProcedurePerformer, ProcedureSource, ProcedureStatus, Role
from medicore.domain.shared.identifiers import AppointmentId, ProcedureId, ProcedureTypeId
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.mappers._json import (
    dict_to_procedure_draft,
    procedure_draft_to_dict,
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


def test_catalog_and_procedures_round_trip(session):
    tenant = build_tenant(slug=f"test-prc-{ProcedureId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@prc.test")
    uow.users.save(doctor)
    ana = build_patient(tenant.id, code="P-00001", first_name="Ana", last_name="Ayala")
    uow.patients.save(ana)
    session.flush()

    biopsy = ProcedureType(id=ProcedureTypeId.new(), tenant_id=tenant.id, name="Biopsia de piel",
                           requires_consent=True, follow_up_days=10, takes_specimen=True,
                           technique_template="Sacabocado", created_at=NOW)
    ecg = ProcedureType(id=ProcedureTypeId.new(), tenant_id=tenant.id, name="Electrocardiograma",
                        performer=ProcedurePerformer.DOCTOR_OR_NURSE, active=False, created_at=NOW)
    uow.procedures.save_type(biopsy)
    uow.procedures.save_type(ecg)
    session.flush()

    appt = AppointmentId.new()
    done = Procedure(
        id=ProcedureId.new(), tenant_id=tenant.id, patient_id=ana.id, type_id=biopsy.id,
        type_name=biopsy.name, performer=biopsy.performer, requires_consent=True,
        source=ProcedureSource.DIRECT, indication="Lesión en espalda", ordered_by_id=doctor.id,
        created_by_id=doctor.id, follow_up_days=10, takes_specimen=True, appointment_id=appt,
        created_at=NOW - timedelta(hours=2),
    )
    done.record_consent("Ana Ayala", None, "Lucía Méndez", doctor.id, NOW - timedelta(hours=1))
    done.save_progress(ProcedureProgress(
        allergies_reviewed=True, anticoagulants=False, technique="Sacabocado 4 mm",
        temp_before=36.6, hr_before=72, specimen_sent=True, specimen_description="Piel, 4 mm",
    ), NOW - timedelta(hours=1))
    done.sign(doctor.id, NOW, date(2026, 6, 5), False)
    done.amend(doctor.id, "Sacabocado de 5 mm", "Medida corregida", NOW + timedelta(minutes=5))
    pending = Procedure(
        id=ProcedureId.new(), tenant_id=tenant.id, patient_id=ana.id, type_id=ecg.id,
        type_name=ecg.name, performer=ecg.performer, requires_consent=False,
        source=ProcedureSource.DIRECT, indication="Palpitaciones", ordered_by_id=doctor.id,
        created_by_id=doctor.id, created_at=NOW,
    )
    uow.procedures.save(done)
    uow.procedures.save(pending)
    session.flush()
    session.expunge_all()

    assert [t.name for t in uow.procedures.list_types()] == ["Biopsia de piel",
                                                             "Electrocardiograma"]
    assert uow.procedures.get_type(ecg.id).active is False
    loaded = uow.procedures.get(done.id)
    assert loaded.status == ProcedureStatus.COMPLETED
    assert (loaded.temp_before, loaded.anticoagulants, loaded.follow_up_on) == (
        36.6, False, date(2026, 6, 15))
    assert loaded.consent_witness == "Lucía Méndez" and loaded.appointment_id == appt
    assert [(a.text, a.by_id) for a in loaded.amendments] == [("Sacabocado de 5 mm", doctor.id)]
    assert [p.id for p in uow.procedures.list_open()] == [pending.id]
    assert [p.id for p in uow.procedures.list_by_patient(ana.id)] == [pending.id, done.id]
    assert [p.id for p in uow.procedures.list_by_appointments([appt])] == [done.id]
    window = uow.procedures.list_completed_between(NOW - timedelta(days=1),
                                                   NOW + timedelta(hours=1))
    assert [p.id for p in window] == [done.id]


def test_procedure_draft_json_round_trip():
    kind = ProcedureType(id=ProcedureTypeId.new(), tenant_id=build_tenant().id, name="Sutura",
                         requires_consent=True, follow_up_days=8)
    d = ProcedureDraft.of(kind, "Herida")
    assert dict_to_procedure_draft(procedure_draft_to_dict(d)) == d
