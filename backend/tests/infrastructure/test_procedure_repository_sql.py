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
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.entities.procedure import (
    Procedure,
    ProcedureDraft,
    ProcedureProgress,
    ProcedureType,
)
from medicore.domain.enums import (
    AppointmentType,
    ProcedurePerformer,
    ProcedureSource,
    ProcedureStatus,
    Role,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    FeeScheduleId,
    ProcedureId,
    ProcedureTypeId,
)
from medicore.domain.value_objects.fee import Charge, fee
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
                         requires_consent=True, follow_up_days=8, price=fee("35.50"))
    d = ProcedureDraft.of(kind, "Herida")
    assert dict_to_procedure_draft(procedure_draft_to_dict(d)) == d
    included = ProcedureDraft.of(kind, "Herida", included=True)
    assert dict_to_procedure_draft(procedure_draft_to_dict(included)) == included
    # drafts saved before fees existed have no price
    legacy = {k: v for k, v in procedure_draft_to_dict(d).items() if k not in ("price", "included")}
    assert (dict_to_procedure_draft(legacy).price, dict_to_procedure_draft(legacy).included) == (
        None, False)


def test_fees_round_trip(session):
    tenant = build_tenant(slug=f"test-fee-{ProcedureId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@fee.test")
    uow.users.save(doctor)
    ana = build_patient(tenant.id, code="P-00001", first_name="Ana", last_name="Ayala")
    uow.patients.save(ana)
    session.flush()

    schedule = FeeSchedule(id=FeeScheduleId.new(), tenant_id=tenant.id, doctor_id=doctor.id)
    schedule.set_prices({AppointmentType.CONSULT: fee(30), AppointmentType.EMERGENCY: fee("45.5")},
                        NOW)
    uow.fees.save(schedule)
    kind = ProcedureType(id=ProcedureTypeId.new(), tenant_id=tenant.id, name="Sutura",
                         price=fee("35.00"), created_at=NOW)
    uow.procedures.save_type(kind)
    appt = Appointment(
        id=AppointmentId.new(), tenant_id=tenant.id, code="A-0001", patient_id=ana.id,
        doctor_id=doctor.id, location_id=tenant.primary_location.id,
        type=AppointmentType.CONSULT, scheduled_start=datetime(2026, 6, 5, 9, 0),
        duration_minutes=30, reason="Control", created_by_id=doctor.id,
        charge=Charge.at_list_price(fee(30)).adjust(fee(25), "Adulto mayor"),
    )
    uow.appointments.save(appt)
    proc = Procedure.from_draft(
        ProcedureDraft.of(kind, "Herida", included=True), tenant_id=tenant.id, patient_id=ana.id,
        ordered_by_id=doctor.id, consultation_id=ConsultationId.new(), now=NOW,
    )
    uow.procedures.save(proc)
    session.flush()
    session.expunge_all()

    assert uow.fees.get_by_doctor(doctor.id).prices == schedule.prices
    assert list(uow.fees.list_for_doctors([doctor.id])) == [doctor.id]
    assert uow.procedures.get_type(kind.id).price == fee(35)
    loaded = uow.appointments.get_by_id(appt.id)
    assert (loaded.charge.listed, loaded.charge.charged, loaded.charge.note) == (
        fee(30), fee(25), "Adulto mayor")
    p = uow.procedures.get(proc.id)
    assert (p.charge.listed, p.charge.charged, p.fee_included) == (fee(35), fee(0), True)
