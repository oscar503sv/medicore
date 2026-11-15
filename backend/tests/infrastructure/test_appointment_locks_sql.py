"""Integration tests: appointment transitions racing consultations (PostgreSQL).

Same harness as ``test_consultation_sign_sql``: a holder session locks a row first so the
competing transactions queue behind it in a known order. Committed rows are removed with
their tenant at the end.
"""

from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from medicore.application.use_cases.appointments import CancelAppointment
from medicore.application.use_cases.consultations import (
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.domain.entities.consultation import Consultation
from medicore.domain.shared.errors import InvalidStateTransition
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId
from tests.infrastructure.test_consultation_sign_sql import NOW, WAIT, Clinic, engine  # noqa: F401
from tests.support.fakes import FixedClock


def _cancel(clinic: Clinic) -> None:
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        CancelAppointment(clinic.uow(session), FixedClock(NOW)).execute(
            clinic.actor, clinic.appointment.id
        )


def _blocked(futures) -> None:
    for future in futures:
        with pytest.raises(FutureTimeout):
            future.result(timeout=WAIT)


def _appointment_status(clinic: Clinic) -> str:
    return clinic.scalar("SELECT status FROM appointments WHERE tenant_id = :t")


def test_cancel_waiting_on_a_consultation_signature_is_refused(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(_cancel, clinic)
            _blocked([future])
            SignConsultation(uow, uow.code_generator(), FixedClock(NOW)).execute(
                clinic.actor, SignConsultationCommand(clinic.consultation.id)
            )
        finally:
            holder.close()

        with pytest.raises(InvalidStateTransition):
            future.result(timeout=10)
        assert _appointment_status(clinic) == "completed"
        assert clinic.scalar("SELECT count(*) FROM medical_records WHERE tenant_id = :t") == 1


def test_cancel_wins_over_a_waiting_start(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM consultations WHERE id = :c"),
                         {"c": clinic.consultation.id.value})
            conn.execute(text("UPDATE appointments SET status = 'scheduled' WHERE tenant_id = :t"),
                         {"t": clinic.tenant.id.value})

        def start() -> None:
            with Session(bind=engine, expire_on_commit=False) as session:
                StartConsultation(clinic.uow(session), FixedClock(NOW)).execute(
                    clinic.actor, clinic.appointment.id
                )

        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(start)
            _blocked([future])
            CancelAppointment(uow, FixedClock(NOW)).execute(clinic.actor, clinic.appointment.id)
        finally:
            holder.close()

        with pytest.raises(InvalidStateTransition):
            future.result(timeout=10)
        assert clinic.scalar("SELECT count(*) FROM consultations WHERE tenant_id = :t") == 0
        assert _appointment_status(clinic) == "cancelled"


def test_cancel_of_an_in_progress_appointment_does_not_wait_on_its_consultation(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).consultations.get_for_update(clinic.consultation.id)
            started = time.monotonic()
            with pytest.raises(InvalidStateTransition):
                pool.submit(_cancel, clinic).result(timeout=5)
            assert time.monotonic() - started < 5
        finally:
            holder.rollback()
            holder.close()
        assert _appointment_status(clinic) == "in_progress"


def _second_consultation(clinic: Clinic) -> Consultation:
    """A second in-progress appointment of the same clinic with a consultation to sign."""
    appointment = copy.copy(clinic.appointment)
    appointment.id = AppointmentId.new()
    appointment.code = "A-2"
    consultation = copy.copy(clinic.consultation)
    consultation.id = ConsultationId.new()
    consultation.appointment_id = appointment.id
    with Session(bind=clinic.engine) as session:
        uow = clinic.uow(session)
        uow.appointments.save(appointment)
        session.flush()
        uow.consultations.save(consultation)
        session.commit()
    return consultation


def test_sign_waiting_on_an_appointment_does_not_hold_the_record_counter(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        other = _second_consultation(clinic)

        def sign_other() -> None:
            with Session(bind=engine, expire_on_commit=False) as session:
                uow = clinic.uow(session)
                SignConsultation(uow, uow.code_generator(), FixedClock(NOW)).execute(
                    clinic.actor, SignConsultationCommand(other.id)
                )

        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.get_for_update(clinic.appointment.id)
            blocked = pool.submit(clinic.sign)
            _blocked([blocked])
            # Were the counter held by the waiting sign, this one would queue behind it too.
            pool.submit(sign_other).result(timeout=5)
            holder.rollback()
        finally:
            holder.close()
        blocked.result(timeout=10)
        assert clinic.scalar("SELECT count(*) FROM medical_records WHERE tenant_id = :t") == 2
