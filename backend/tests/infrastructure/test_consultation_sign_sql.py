"""Integration tests: signing and editing one consultation concurrently (PostgreSQL).

Real concurrent connections, so committed rows are created and removed explicitly; SKIP when
PostgreSQL is unreachable. The index tests run in a rolled-back transaction.
"""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.application.common.context import ActorContext
from medicore.application.use_cases.consultations import (
    AutosaveConsultation,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.domain.entities.application import ApplicationDraft
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import (
    ApplicationRoute,
    AppointmentType,
    ClinicalRecordType,
    Role,
)
from medicore.domain.shared.errors import ConsultationAlreadySigned
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId, RecordId
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user, soap_note
from tests.support.fakes import FixedClock

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
WAIT = 0.5


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


class Clinic:
    """A committed tenant with a doctor, a patient, an appointment and a signable draft."""

    def __init__(self, engine, *, started: bool = True) -> None:
        self.engine = engine
        self.tenant = build_tenant(f"csign-{uuid.uuid4().hex[:10]}")
        self.doctor = build_user(self.tenant.id, Role.DOCTOR, email="doc@csign.test")
        self.patient = build_patient(self.tenant.id, code="P-00001")
        self.actor = ActorContext(
            user_id=self.doctor.id, tenant_id=self.tenant.id, role=Role.DOCTOR
        )
        self.appointment = Appointment(
            id=AppointmentId.new(), tenant_id=self.tenant.id, code="A-1",
            patient_id=self.patient.id, doctor_id=self.doctor.id,
            location_id=self.tenant.primary_location.id, type=AppointmentType.CONSULT,
            scheduled_start=datetime(2026, 6, 1, 9, 0), duration_minutes=30, reason="Control",
            created_by_id=self.doctor.id,
        )
        self.consultation = Consultation(
            id=ConsultationId.new(), tenant_id=self.tenant.id,
            appointment_id=self.appointment.id, patient_id=self.patient.id,
            doctor_id=self.doctor.id, started_at=NOW,
        )
        self.consultation.autosave(
            note=soap_note("s", "o", "a", "p").texts(),
            vitals={"heart_rate": 72, "weight": Decimal("70")},
        )
        self.consultation.add_diagnosis(IcdCode("I10", "Hipertensión"))
        self.consultation.add_prescription_draft(
            PrescriptionDraft(drug="Enalapril", dose="20 mg", schedule="1x", duration_days=30)
        )
        self.consultation.add_application_draft(
            ApplicationDraft(drug="Ketorolaco", dose="30 mg", route=ApplicationRoute.INTRAMUSCULAR)
        )
        self.appointment.start()

    def __enter__(self) -> Clinic:
        with Session(bind=self.engine) as session:
            uow = SqlAlchemyUnitOfWork(session, self.tenant.id)
            uow.tenants.save(self.tenant)
            session.flush()
            uow.users.save(self.doctor)
            uow.patients.save(self.patient)
            session.flush()
            uow.appointments.save(self.appointment)
            session.flush()
            uow.consultations.save(self.consultation)
            session.commit()
        return self

    def __exit__(self, *exc) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(TenantModel).where(TenantModel.id == self.tenant.id.value))

    def uow(self, session: Session) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session, self.tenant.id)

    def sign(self) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            uow = self.uow(session)
            SignConsultation(uow, uow.code_generator(), FixedClock(NOW)).execute(
                self.actor, SignConsultationCommand(self.consultation.id)
            )

    def autosave(self) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            AutosaveConsultation(self.uow(session), FixedClock(NOW)).execute(
                self.actor, self.consultation.id, ConsultationPatch(note={"plan": "late"})
            )

    def scalar(self, sql: str):
        with self.engine.connect() as conn:
            return conn.execute(
                text(sql), {"t": self.tenant.id.value, "c": self.consultation.id.value}
            ).scalar()


def test_concurrent_signs_store_one_record(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).consultations.get_for_update(clinic.consultation.id)
            futures = [pool.submit(clinic.sign) for _ in range(2)]
            for future in futures:
                with pytest.raises(FutureTimeout):
                    future.result(timeout=WAIT)
            holder.rollback()
        finally:
            holder.close()

        outcomes = []
        for future in futures:
            try:
                future.result(timeout=10)
                outcomes.append("signed")
            except ConsultationAlreadySigned:
                outcomes.append("refused")

        assert sorted(outcomes) == ["refused", "signed"]
        count = "SELECT count(*) FROM {} WHERE tenant_id = :t"
        assert clinic.scalar(count.format("medical_records")) == 1
        assert clinic.scalar(count.format("prescriptions")) == 1
        assert clinic.scalar(count.format("application_orders")) == 1
        assert clinic.scalar("SELECT status FROM consultations WHERE id = :c") == "signed"
        assert clinic.scalar("SELECT status FROM appointments WHERE tenant_id = :t") == "completed"
        assert (
            clinic.scalar(
                "SELECT last_value FROM tenant_counters WHERE tenant_id = :t AND series = 'record'"
            )
            == 1
        )


def test_edit_waiting_on_a_sign_is_refused(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.consultations.get_for_update(clinic.consultation.id)
            future = pool.submit(clinic.autosave)
            with pytest.raises(FutureTimeout):
                future.result(timeout=WAIT)
            SignConsultation(uow, uow.code_generator(), FixedClock(NOW)).execute(
                clinic.actor, SignConsultationCommand(clinic.consultation.id)
            )
        finally:
            holder.close()

        with pytest.raises(ConsultationAlreadySigned):
            future.result(timeout=10)
        assert clinic.scalar("SELECT status FROM consultations WHERE id = :c") == "signed"


def test_concurrent_starts_return_one_consultation(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM consultations WHERE id = :c"),
                         {"c": clinic.consultation.id.value})
            conn.execute(text("UPDATE appointments SET status = 'scheduled' WHERE tenant_id = :t"),
                         {"t": clinic.tenant.id.value})

        def start() -> ConsultationId:
            with Session(bind=engine, expire_on_commit=False) as session:
                return StartConsultation(clinic.uow(session), FixedClock(NOW)).execute(
                    clinic.actor, clinic.appointment.id
                ).id

        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.get_for_update(clinic.appointment.id)
            futures = [pool.submit(start) for _ in range(2)]
            for future in futures:
                with pytest.raises(FutureTimeout):
                    future.result(timeout=WAIT)
            holder.rollback()
        finally:
            holder.close()

        ids = {future.result(timeout=10) for future in futures}
        assert len(ids) == 1
        assert clinic.scalar("SELECT count(*) FROM consultations WHERE tenant_id = :t") == 1


def test_appointment_lock_does_not_block_consultation_inserts(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM consultations WHERE id = :c"),
                         {"c": clinic.consultation.id.value})
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.get_for_update(clinic.appointment.id)

            def insert() -> None:
                with Session(bind=engine) as session:
                    uow = clinic.uow(session)
                    uow.consultations.save(clinic.consultation)
                    session.commit()

            # A plain FOR UPDATE would hold this insert back (its FK check takes FOR KEY SHARE).
            pool.submit(insert).result(timeout=5)
        finally:
            holder.rollback()
            holder.close()


@pytest.fixture
def clinic_session(engine):
    clinic = Clinic(engine)
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    uow.tenants.save(clinic.tenant)
    session.flush()
    yield clinic, session
    session.close()
    trans.rollback()
    connection.close()


def _record(clinic, consultation_id, amends=None) -> MedicalRecord:
    return MedicalRecord(
        id=RecordId.new(), tenant_id=clinic.tenant.id, code=f"REC-{uuid.uuid4().hex[:8]}",
        patient_id=clinic.patient.id, author_id=clinic.doctor.id,
        type=ClinicalRecordType.CONSULTATION, encounter_at=NOW, location_name="Sede",
        chief_complaint="x", note=soap_note(), vitals=Vitals(), signed_at=NOW,
        signed_by_id=clinic.doctor.id, consultation_id=consultation_id, amends_record_id=amends,
        amendment_reason="Corrección del motivo" if amends else None,
    )


def test_index_refuses_a_second_original_record(clinic_session):
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    uow.users.save(clinic.doctor)
    uow.patients.save(clinic.patient)
    session.flush()
    consultation_id = ConsultationId.new()
    uow.medical_records.save(_record(clinic, consultation_id))
    session.flush()

    with pytest.raises(IntegrityError), session.begin_nested():
        uow.medical_records.save(_record(clinic, consultation_id))
        session.flush()


def test_index_accepts_amendments_and_records_without_consultation(clinic_session):
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    uow.users.save(clinic.doctor)
    uow.patients.save(clinic.patient)
    session.flush()
    consultation_id = ConsultationId.new()
    original = _record(clinic, consultation_id)
    uow.medical_records.save(original)
    uow.medical_records.save(_record(clinic, consultation_id, amends=original.id))
    uow.medical_records.save(_record(clinic, None))
    uow.medical_records.save(_record(clinic, None))
    session.flush()
