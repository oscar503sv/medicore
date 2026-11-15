"""Integration tests: signing and editing one procedure concurrently (PostgreSQL).

Real concurrent connections, so committed rows are created and removed explicitly; SKIP when
PostgreSQL is unreachable. A "holder" session locks the row first so the competing
transactions are queued deterministically behind it.
"""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.appointments import CancelAppointment
from medicore.application.use_cases.fees import AdjustAppointmentFee
from medicore.application.use_cases.procedures import (
    CreateProcedure,
    CreateProcedureCommand,
    SaveProcedureProgress,
    SignProcedure,
)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.procedure import (
    Procedure,
    ProcedureAlreadySigned,
    ProcedureProgress,
    ProcedureType,
)
from medicore.domain.enums import AppointmentType, ProcedurePerformer, ProcedureSource, Role
from medicore.domain.shared.identifiers import AppointmentId, ProcedureId, ProcedureTypeId
from medicore.domain.value_objects.fee import fee
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user
from tests.support.fakes import FixedClock

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
WAIT = 0.5
READY = ProcedureProgress(allergies_reviewed=True, technique="Sutura simple")


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
    """A committed tenant with a doctor, a patient, a procedure appointment in progress and
    a procedure on it ready to be signed."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.tenant = build_tenant(f"psign-{uuid.uuid4().hex[:10]}")
        self.doctor = build_user(self.tenant.id, Role.DOCTOR, email="doc@psign.test")
        self.patient = build_patient(self.tenant.id, code="P-00001")
        self.actor = ActorContext(
            user_id=self.doctor.id, tenant_id=self.tenant.id, role=Role.DOCTOR
        )
        self.kind = ProcedureType(
            id=ProcedureTypeId.new(), tenant_id=self.tenant.id, name="Sutura",
            performer=ProcedurePerformer.DOCTOR, price=fee("20"),
        )
        self.appointment = self._appointment()
        self.procedure = Procedure(
            id=ProcedureId.new(), tenant_id=self.tenant.id, patient_id=self.patient.id,
            type_id=self.kind.id, type_name=self.kind.name, performer=self.kind.performer,
            requires_consent=False, source=ProcedureSource.DIRECT, indication="Herida",
            ordered_by_id=self.doctor.id, created_by_id=self.doctor.id,
            appointment_id=self.appointment.id, created_at=NOW,
        )
        self.procedure.save_progress(READY, NOW)

    def _appointment(self, code: str = "A-1") -> Appointment:
        return Appointment(
            id=AppointmentId.new(), tenant_id=self.tenant.id, code=code,
            patient_id=self.patient.id, doctor_id=self.doctor.id,
            location_id=self.tenant.primary_location.id, type=AppointmentType.PROCEDURE,
            scheduled_start=datetime(2026, 6, 1, 9, 0), duration_minutes=30, reason="Sutura",
            created_by_id=self.doctor.id,
        )

    def __enter__(self) -> Clinic:
        with Session(bind=self.engine) as session:
            uow = SqlAlchemyUnitOfWork(session, self.tenant.id)
            uow.tenants.save(self.tenant)
            session.flush()
            uow.users.save(self.doctor)
            uow.patients.save(self.patient)
            uow.procedures.save_type(self.kind)
            session.flush()
            uow.appointments.save(self.appointment)
            session.flush()
            uow.procedures.save(self.procedure)
            session.commit()
        return self

    def __exit__(self, *exc) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(TenantModel).where(TenantModel.id == self.tenant.id.value))

    def uow(self, session: Session) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session, self.tenant.id)

    def sign(self) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            SignProcedure(self.uow(session), FixedClock(NOW)).execute(
                self.actor, self.procedure.id
            )

    def save_progress(self) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            SaveProcedureProgress(self.uow(session), FixedClock(NOW)).execute(
                self.actor, self.procedure.id,
                ProcedureProgress(allergies_reviewed=True, technique="Late edit"),
            )

    def adjust_fee(self) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            AdjustAppointmentFee(self.uow(session), FixedClock(NOW)).execute(
                self.actor, self.appointment.id, fee("35"), "Insumos extra"
            )

    def create_procedure(self) -> Procedure:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            return CreateProcedure(self.uow(session), FixedClock(NOW)).execute(
                self.actor,
                CreateProcedureCommand(
                    self.patient.id, self.kind.id, "Otra herida", self.appointment.id
                ),
            )

    def scalar(self, sql: str):
        with self.engine.connect() as conn:
            return conn.execute(
                text(sql),
                {
                    "t": self.tenant.id.value,
                    "p": self.procedure.id.value,
                    "a": self.appointment.id.value,
                },
            ).scalar()


def _blocked(futures) -> None:
    """Every competing call is still waiting behind the holder."""
    for future in futures:
        with pytest.raises(FutureTimeout):
            future.result(timeout=WAIT)


def test_concurrent_signs_store_one_signature(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).procedures.get_for_update(clinic.procedure.id)
            futures = [pool.submit(clinic.sign) for _ in range(2)]
            _blocked(futures)
            holder.rollback()
        finally:
            holder.close()

        outcomes = []
        for future in futures:
            try:
                future.result(timeout=10)
                outcomes.append("signed")
            except ProcedureAlreadySigned:
                outcomes.append("refused")

        assert sorted(outcomes) == ["refused", "signed"]
        assert clinic.scalar("SELECT status FROM procedures WHERE id = :p") == "completed"
        assert clinic.scalar("SELECT status FROM appointments WHERE id = :a") == "completed"
        assert clinic.scalar(
            "SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND action = 'procedure.signed'"
        ) == 1


def test_late_save_waiting_on_a_signature_is_refused(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.procedures.get_for_update(clinic.procedure.id)
            future = pool.submit(clinic.save_progress)
            _blocked([future])
            SignProcedure(uow, FixedClock(NOW)).execute(clinic.actor, clinic.procedure.id)
        finally:
            holder.close()

        with pytest.raises(ProcedureAlreadySigned):
            future.result(timeout=10)
        assert clinic.scalar("SELECT status FROM procedures WHERE id = :p") == "completed"
        assert clinic.scalar("SELECT technique FROM procedures WHERE id = :p") == "Sutura simple"


def test_signature_waiting_on_a_cancellation_keeps_the_appointment_cancelled(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as conn:
            conn.execute(text("UPDATE appointments SET status = 'scheduled' WHERE id = :a"),
                         {"a": clinic.appointment.id.value})
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(clinic.sign)
            _blocked([future])
            CancelAppointment(uow, FixedClock(NOW)).execute(clinic.actor, clinic.appointment.id)
        finally:
            holder.close()

        future.result(timeout=10)
        assert clinic.scalar("SELECT status FROM procedures WHERE id = :p") == "completed"
        assert clinic.scalar("SELECT status FROM appointments WHERE id = :a") == "cancelled"


def test_fee_adjustment_does_not_revert_the_signature(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.procedures.get_for_update(clinic.procedure.id)
            uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(clinic.adjust_fee)
            _blocked([future])
            SignProcedure(uow, FixedClock(NOW)).execute(clinic.actor, clinic.procedure.id)
        finally:
            holder.close()

        future.result(timeout=10)
        assert clinic.scalar("SELECT status FROM appointments WHERE id = :a") == "completed"
        assert clinic.scalar("SELECT fee FROM appointments WHERE id = :a") == 35


def test_double_registration_on_one_appointment_creates_one_procedure(engine):
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM procedures WHERE id = :p"),
                         {"p": clinic.procedure.id.value})
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.get_for_update(clinic.appointment.id)
            futures = [pool.submit(clinic.create_procedure) for _ in range(2)]
            _blocked(futures)
            holder.rollback()
        finally:
            holder.close()

        outcomes = []
        for future in futures:
            try:
                future.result(timeout=10)
                outcomes.append("created")
            except ValidationError as error:
                assert error.code == "procedure.appointment_taken"
                outcomes.append("refused")

        assert sorted(outcomes) == ["created", "refused"]
        assert clinic.scalar(
            "SELECT count(*) FROM procedures WHERE tenant_id = :t AND status <> 'cancelled'"
        ) == 1
