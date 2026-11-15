"""Integration tests: signed records are protected in PostgreSQL itself (append-only trigger,
foreign keys, the prescription trigger, the seal that survives storage, the controlled purge).

Signing and purging use committed rows (the ``Clinic`` harness of the consultation sign
tests, which purges its tenant on exit); everything else runs in a rolled-back transaction.
Skipped when PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from medicore.application.use_cases.records import AmendMedicalRecord, GetMedicalRecord
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import SealStatus
from medicore.domain.services.record_seal import verify_chain
from medicore.domain.shared.errors import RecordTampered
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    RecordId,
    UserId,
)
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.database.tenant_purge import purge_tenants
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.domain.services.test_record_seal import make_record
from tests.infrastructure.test_consultation_sign_sql import (  # noqa: F401
    NOW,
    Clinic,
    _record,
    _save_the_booking,
    clinic_session,
    engine,
)
from tests.support.fakes import FixedClock
from tests.support.records import sealed

RESTRICT_VIOLATION = "23001"
GUARDED_TRIGGERS = (
    "trg_medical_records_append_only",
    "trg_medical_records_no_truncate",
    "trg_prescriptions_closing_only",
    "trg_prescriptions_no_truncate",
)
REASON = "Se corrige el motivo de consulta"


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _rich(clinic, *, previous: MedicalRecord | None = None, **overrides) -> MedicalRecord:
    """A record with every kind of content, tied to the clinic's real rows."""
    fields = dict(
        id=RecordId.new(), tenant_id=clinic.tenant.id, patient_id=clinic.patient.id,
        author_id=clinic.doctor.id, signed_by_id=clinic.doctor.id,
        appointment_id=clinic.appointment.id, consultation_id=clinic.consultation.id,
        code=f"REC-{uuid.uuid4().hex[:8]}", encounter_at=NOW, signed_at=NOW + timedelta(hours=1),
    )
    record = replace(make_record(**{**fields, **overrides}), seal=None)
    return sealed(record, previous)


def _triggers(connection) -> dict[str, str]:
    rows = connection.execute(text(
        "SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = ANY(:names)"
    ), {"names": list(GUARDED_TRIGGERS)}).all()
    return dict(rows)


def _clinic_with_a_record(clinic_session):  # noqa: F811
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    _save_the_booking(uow, session, clinic)
    record = _rich(clinic)
    uow.medical_records.save(record)
    session.flush()
    return clinic, session, uow, record


# ── the seal survives storage ───────────────────────────────────────────────────────────


def test_a_chain_of_three_verifies_after_a_round_trip(clinic_session):  # noqa: F811
    clinic, session, uow, original = _clinic_with_a_record(clinic_session)
    first = _rich(clinic, previous=original, status="amended", amends_record_id=original.id,
                  amendment_reason=REASON, chief_complaint="Cefalea 😀 áéíóú ñ",
                  signed_at=NOW + timedelta(days=1))
    second = _rich(clinic, previous=first, status="amended", amends_record_id=first.id,
                   amendment_reason=REASON, insurer_name=None,
                   vitals=Vitals(temperature=Decimal("36.50"), weight=Decimal("70.00")),
                   signed_at=NOW + timedelta(days=2))
    for record in (first, second):
        uow.medical_records.save(record)
    session.flush()
    session.expire_all()

    chain = uow.medical_records.versions(second.id)

    assert [r.id for r in chain] == [original.id, first.id, second.id]
    assert verify_chain(chain) == (SealStatus.OK,) * 3
    assert chain[2].insurer_name is None and chain[2].vitals.temperature == Decimal("36.50")


def test_the_seal_does_not_depend_on_the_session_time_zone(clinic_session):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    for zone in ("Asia/Tokyo", "America/El_Salvador", "UTC"):
        session.execute(text(f"SET LOCAL TIME ZONE '{zone}'"))
        session.expire_all()
        assert verify_chain(uow.medical_records.versions(record.id)) == (SealStatus.OK,)


@pytest.mark.parametrize("seal", ["ZZ", "A" * 64, "a" * 63, ""])
def test_the_database_refuses_a_malformed_seal(clinic_session, seal):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    with pytest.raises(IntegrityError), session.begin_nested():
        # A copy of the stored row with another id and the bad seal: the repository never
        # writes one, so the CHECK is reached with SQL.
        session.execute(text(
            "INSERT INTO medical_records (id, tenant_id, code, patient_id, author_id, type, "
            "status, encounter_at, location_name, chief_complaint, note, vitals, diagnoses, "
            "prescriptions, vaccines, exams, attachments, signed_at, signed_by_id, seal, "
            "seal_version) SELECT :id, tenant_id, 'X', patient_id, author_id, type, status, "
            "encounter_at, location_name, chief_complaint, note, vitals, diagnoses, "
            "prescriptions, vaccines, exams, attachments, signed_at, signed_by_id, :seal, 1 "
            "FROM medical_records WHERE id = :src"
        ), {"id": uuid.uuid4(), "src": record.id.value, "seal": seal})


# ── append-only ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("statement", [
    "UPDATE medical_records SET chief_complaint = 'otra cosa'",
    "UPDATE medical_records SET chief_complaint = chief_complaint",
    "UPDATE medical_records SET seal = repeat('0', 64)",
    "DELETE FROM medical_records",
    "TRUNCATE medical_records CASCADE",
])
def test_a_signed_record_cannot_be_updated_deleted_or_truncated(clinic_session, statement):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    where = "" if statement.startswith("TRUNCATE") else " WHERE id = :id"

    with pytest.raises(DBAPIError) as exc, session.begin_nested():
        session.execute(text(statement + where), {"id": record.id.value} if where else {})

    assert _sqlstate(exc.value) == RESTRICT_VIOLATION
    assert "append-only" in str(exc.value)
    session.expire_all()
    assert uow.medical_records.get_by_id(record.id) == record


def test_the_triggers_fire_even_in_replica_mode(clinic_session):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    try:
        with session.begin_nested():
            session.execute(text("SET LOCAL session_replication_role = replica"))
    except DBAPIError:
        pytest.skip("changing session_replication_role needs a superuser")

    with pytest.raises(DBAPIError) as exc, session.begin_nested():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(text("DELETE FROM medical_records WHERE id = :id"),
                        {"id": record.id.value})
    assert _sqlstate(exc.value) == RESTRICT_VIOLATION


def test_the_triggers_are_always_enabled(engine):  # noqa: F811
    with engine.connect() as connection:
        assert _triggers(connection) == dict.fromkeys(GUARDED_TRIGGERS, "A")


# ── foreign keys ────────────────────────────────────────────────────────────────────────


def test_a_clinic_with_signed_records_cannot_be_deleted(clinic_session):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": clinic.tenant.id.value})


@pytest.mark.parametrize("field", ["patient_id", "consultation_id", "appointment_id",
                                   "author_id", "signed_by_id"])
def test_a_record_cannot_point_at_nothing(clinic_session, field):  # noqa: F811
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    _save_the_booking(uow, session, clinic)
    ghosts = {
        "patient_id": PatientId.new(), "consultation_id": ConsultationId.new(),
        "appointment_id": AppointmentId.new(), "author_id": UserId.new(),
        "signed_by_id": UserId.new(),
    }
    with pytest.raises(IntegrityError), session.begin_nested():
        uow.medical_records.save(_rich(clinic, **{field: ghosts[field]}))
        session.flush()


def test_a_prescription_cannot_point_at_a_missing_record(clinic_session):  # noqa: F811
    clinic, session, uow, record = _clinic_with_a_record(clinic_session)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text(
            "INSERT INTO prescriptions (id, tenant_id, patient_id, prescriber_id, drug, dose, "
            "schedule, start_date, status, record_id) VALUES (:id, :t, :p, :d, 'x', 'x', 'x', "
            "'2026-06-01', 'active', :r)"
        ), {"id": uuid.uuid4(), "t": clinic.tenant.id.value, "p": clinic.patient.id.value,
            "d": clinic.doctor.id.value, "r": uuid.uuid4()})


# ── signing writes the record and its prescriptions in one flush ───────────────────────


def test_signing_with_a_prescription_orders_the_inserts_for_the_foreign_key(engine):  # noqa: F811
    with Clinic(engine) as clinic:
        clinic.sign()

        assert clinic.scalar("SELECT count(*) FROM prescriptions p JOIN medical_records r "
                             "ON r.id = p.record_id WHERE p.tenant_id = :t") == 1
        record_id = RecordId.parse(
            clinic.scalar("SELECT id FROM medical_records WHERE tenant_id = :t"))
        with Session(bind=engine) as session:
            chain = clinic.uow(session).medical_records.versions(record_id)
        assert verify_chain(chain) == (SealStatus.OK,)


# ── the prescription trigger ────────────────────────────────────────────────────────────


@pytest.fixture
def signed_clinic(engine):  # noqa: F811
    with Clinic(engine) as clinic:
        clinic.sign()
        yield clinic


def _in_rolled_back_tx(db, statements: list[tuple[str, dict]], clinic):
    """Runs the statements in order inside one transaction that is always rolled back;
    returns the SQLSTATE of the first one that fails (or None)."""
    with db.connect() as conn:
        tx = conn.begin()
        try:
            for sql, params in statements:
                conn.execute(text(sql), {"t": clinic.tenant.id.value, **params})
        except DBAPIError as exc:
            return _sqlstate(exc)
        finally:
            tx.rollback()
    return None


CLOSE = ("UPDATE prescriptions SET status = :s, closed_at = now(), closed_by_id = :u"
         ", cancel_reason = :r WHERE tenant_id = :t")


def test_an_active_prescription_can_be_completed_and_cancelled(signed_clinic, engine):  # noqa: F811
    doctor = {"u": signed_clinic.doctor.id.value}
    assert _in_rolled_back_tx(
        engine, [(CLOSE, {**doctor, "s": "completed", "r": None})], signed_clinic) is None
    assert _in_rolled_back_tx(
        engine, [(CLOSE, {**doctor, "s": "cancelled", "r": "Reacción adversa"})],
        signed_clinic) is None


@pytest.mark.parametrize("statement", [
    "UPDATE prescriptions SET drug = 'Otro' WHERE tenant_id = :t",
    "UPDATE prescriptions SET dose = '999 mg', status = 'completed', closed_at = now() "
    "WHERE tenant_id = :t",
    "UPDATE prescriptions SET record_id = NULL WHERE tenant_id = :t",
    "UPDATE prescriptions SET status = 'active', cancel_reason = 'x' WHERE tenant_id = :t",
    "DELETE FROM prescriptions WHERE tenant_id = :t",
    "TRUNCATE prescriptions CASCADE",
])
def test_a_prescription_cannot_change_beyond_being_closed(signed_clinic, engine, statement):  # noqa: F811
    assert _in_rolled_back_tx(engine, [(statement, {})], signed_clinic) == RESTRICT_VIOLATION


def test_a_closed_prescription_is_final(signed_clinic, engine):  # noqa: F811
    doctor = {"u": signed_clinic.doctor.id.value}
    reopen = "UPDATE prescriptions SET status = 'active' WHERE tenant_id = :t"
    again = (CLOSE, {**doctor, "s": "cancelled", "r": "otra vez"})
    first = (CLOSE, {**doctor, "s": "completed", "r": None})
    assert _in_rolled_back_tx(engine, [first, (reopen, {})], signed_clinic) == RESTRICT_VIOLATION
    assert _in_rolled_back_tx(engine, [first, again], signed_clinic) == RESTRICT_VIOLATION


def test_a_no_op_update_of_a_prescription_is_harmless(signed_clinic, engine):  # noqa: F811
    assert _in_rolled_back_tx(
        engine, [("UPDATE prescriptions SET drug = drug WHERE tenant_id = :t", {})],
        signed_clinic) is None


# ── a record altered behind the application's back is detected ─────────────────────────


def test_an_edit_that_bypasses_the_trigger_is_detected_and_blocks_amending(engine):  # noqa: F811
    with Clinic(engine) as clinic:
        clinic.sign()
        record_id = RecordId.parse(
            clinic.scalar("SELECT id FROM medical_records WHERE tenant_id = :t"))
        # What a careless migration or a DBA with a shortcut would do, in one transaction.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE medical_records DISABLE TRIGGER "
                              "trg_medical_records_append_only"))
            conn.execute(text("UPDATE medical_records SET chief_complaint = 'Alterado' "
                              "WHERE id = :id"), {"id": record_id.value})
            conn.execute(text("ALTER TABLE medical_records ENABLE ALWAYS TRIGGER "
                              "trg_medical_records_append_only"))

        with Session(bind=engine, expire_on_commit=False) as session:
            uow = clinic.uow(session)
            view = GetMedicalRecord(uow, FixedClock(NOW)).execute(clinic.actor, record_id)
        assert view.integrity == SealStatus.TAMPERED
        assert clinic.scalar("SELECT count(*) FROM audit_logs WHERE tenant_id = :t "
                             "AND action = 'record.integrity_failed'") == 1

        with Session(bind=engine, expire_on_commit=False) as session, pytest.raises(
            RecordTampered
        ):
            AmendMedicalRecord(clinic.uow(session), FixedClock(NOW)).execute(
                clinic.actor, record_id, reason=REASON, chief_complaint="Corregido"
            )
        assert clinic.scalar("SELECT count(*) FROM medical_records WHERE tenant_id = :t") == 1


# ── the controlled purge ────────────────────────────────────────────────────────────────


def test_purge_removes_only_the_given_clinics_and_restores_the_triggers(engine):  # noqa: F811
    with Clinic(engine) as gone, Clinic(engine) as kept:
        gone.sign()
        kept.sign()

        with engine.begin() as conn:
            purge_tenants(conn, [gone.tenant.id.value])

        assert gone.scalar("SELECT count(*) FROM tenants WHERE id = :t") == 0
        for table in ("medical_records", "prescriptions", "patients"):
            assert gone.scalar(f"SELECT count(*) FROM {table} WHERE tenant_id = :t") == 0
        assert kept.scalar("SELECT count(*) FROM medical_records WHERE tenant_id = :t") == 1
        assert kept.scalar("SELECT count(*) FROM prescriptions WHERE tenant_id = :t") == 1
        with engine.connect() as connection:
            assert _triggers(connection) == dict.fromkeys(GUARDED_TRIGGERS, "A")
        assert _in_rolled_back_tx(
            engine, [("DELETE FROM medical_records WHERE tenant_id = :t", {})], kept
        ) == RESTRICT_VIOLATION


def test_a_failed_purge_leaves_the_triggers_enabled(engine):  # noqa: F811
    with Clinic(engine) as clinic:
        clinic.sign()
        with pytest.raises(RuntimeError, match="boom"), engine.begin() as conn:
            purge_tenants(conn, [clinic.tenant.id.value])
            raise RuntimeError("boom")

        assert clinic.scalar("SELECT count(*) FROM medical_records WHERE tenant_id = :t") == 1
        with engine.connect() as connection:
            assert _triggers(connection) == dict.fromkeys(GUARDED_TRIGGERS, "A")


def test_purging_nobody_does_nothing(engine):  # noqa: F811
    with engine.begin() as conn:
        purge_tenants(conn, [])
