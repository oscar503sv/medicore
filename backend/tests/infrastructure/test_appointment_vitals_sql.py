"""Integration tests: waiting-room vitals racing the start and the signature (PostgreSQL).

Same harness as ``test_appointment_locks_sql``: a holder session locks a row first so the
competing transactions queue behind it in a known order.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from medicore.application.use_cases.consultations import (
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
    UpdateAppointmentVitals,
)
from medicore.domain.shared.errors import ConsultationAlreadySigned
from tests.infrastructure.test_appointment_locks_sql import _blocked
from tests.infrastructure.test_consultation_sign_sql import NOW, Clinic, engine  # noqa: F401
from tests.support.fakes import FixedClock


def _wait_in_the_waiting_room(clinic: Clinic) -> None:
    """Turn the clinic's started visit into a confirmed one with no consultation yet."""
    with clinic.engine.begin() as conn:
        conn.execute(text("DELETE FROM consultations WHERE id = :c"),
                     {"c": clinic.consultation.id.value})
        conn.execute(text("UPDATE appointments SET status = 'confirmed' WHERE tenant_id = :t"),
                     {"t": clinic.tenant.id.value})


def _record(clinic: Clinic, **changes):
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        return UpdateAppointmentVitals(clinic.uow(session), FixedClock(NOW)).execute(
            clinic.actor, clinic.appointment.id, changes
        )


def _vital(clinic: Clinic, table: str, key: str):
    where = "id = :c" if table == "consultations" else "tenant_id = :t"
    column = "pre_vitals" if table == "appointments" else "vitals"
    return clinic.scalar(f"SELECT {column}->>'{key}' FROM {table} WHERE {where}")


def test_a_write_waiting_for_the_start_ends_up_in_the_consultation(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        _wait_in_the_waiting_room(clinic)
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(_record, clinic, heart_rate=70)
            _blocked([future])
            started = StartConsultation(uow, FixedClock(NOW)).execute(
                clinic.actor, clinic.appointment.id
            )
        finally:
            holder.close()

        view = future.result(timeout=10)
        assert view.phase == "consultation" and view.consultation.id == started.id
        assert clinic.scalar("SELECT count(*) FROM consultations WHERE tenant_id = :t") == 1
        stored = clinic.scalar("SELECT vitals->>'heart_rate' FROM consultations "
                               "WHERE tenant_id = :t")
        assert stored == "70"
        assert _vital(clinic, "appointments", "heart_rate") is None


def test_a_start_waiting_for_a_write_carries_it_into_the_consultation(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        _wait_in_the_waiting_room(clinic)

        def start() -> None:
            with Session(bind=engine, expire_on_commit=False) as session:
                StartConsultation(clinic.uow(session), FixedClock(NOW)).execute(
                    clinic.actor, clinic.appointment.id
                )

        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            appointment = uow.appointments.get_for_update(clinic.appointment.id)
            future = pool.submit(start)
            _blocked([future])
            appointment.record_pre_vitals({"heart_rate": 70}, NOW)
            uow.appointments.save(appointment)
            uow.commit()
        finally:
            holder.close()

        future.result(timeout=10)
        stored = clinic.scalar("SELECT vitals->>'heart_rate' FROM consultations "
                               "WHERE tenant_id = :t")
        assert stored == "70"
        assert _vital(clinic, "appointments", "heart_rate") is None
        assert clinic.scalar("SELECT pre_vitals_saved_at FROM appointments "
                             "WHERE tenant_id = :t") is None


def test_a_write_to_the_consultation_waits_for_the_signature_without_deadlock(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        holder = Session(bind=engine, expire_on_commit=False)
        try:
            uow = clinic.uow(holder)
            uow.consultations.get_for_update(clinic.consultation.id)
            future = pool.submit(_record, clinic, heart_rate=99)
            _blocked([future])
            SignConsultation(uow, uow.code_generator(), FixedClock(NOW)).execute(
                clinic.actor, SignConsultationCommand(clinic.consultation.id)
            )
        finally:
            holder.close()

        with pytest.raises(ConsultationAlreadySigned):
            future.result(timeout=10)
        assert clinic.scalar("SELECT status FROM consultations WHERE id = :c") == "signed"
        assert _vital(clinic, "consultations", "heart_rate") == "72"


def test_pre_vitals_round_trip_and_are_cleared_by_a_cancellation(engine):  # noqa: F811
    with Clinic(engine) as clinic:
        _wait_in_the_waiting_room(clinic)
        _record(clinic, weight=Decimal("70.5"), blood_pressure="120/80")

        with Session(bind=engine) as session:
            appointment = clinic.uow(session).appointments.get_by_id(clinic.appointment.id)
        assert appointment.pre_vitals.weight == Decimal("70.5")
        assert appointment.pre_vitals.blood_pressure == "120/80"
        assert appointment.pre_vitals_saved_at is not None

        with Session(bind=engine) as session:
            uow = clinic.uow(session)
            appointment.cancel()
            uow.appointments.save(appointment)
            uow.commit()
        assert _vital(clinic, "appointments", "weight") is None
        assert clinic.scalar("SELECT pre_vitals_saved_at FROM appointments "
                             "WHERE tenant_id = :t") is None
