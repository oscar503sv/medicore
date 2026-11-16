"""Integration tests: simultaneous bookings of one doctor's slot (PostgreSQL).

Same harness as ``test_appointment_locks_sql``: a holder session takes the doctor's booking
lock first so the competing transactions queue behind it in a known order.
"""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from medicore.application.common.context import ActorContext
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
    RescheduleAppointment,
)
from medicore.domain.enums import AppointmentType, Role
from medicore.domain.shared.errors import SlotUnavailable
from medicore.domain.shared.identifiers import AppointmentId
from tests.infrastructure.test_consultation_sign_sql import WAIT, Clinic, engine  # noqa: F401
from tests.support.builders import build_user, build_weekday_availability
from tests.support.fakes import FixedClock

BOOKING_CLOCK = datetime(2026, 5, 31, 9, 0)
SLOT = datetime(2026, 6, 1, 10, 0)
OTHER_SLOT = datetime(2026, 6, 1, 11, 0)


def _receptionist(clinic: Clinic) -> ActorContext:
    return ActorContext(
        user_id=clinic.doctor.id, tenant_id=clinic.tenant.id, role=Role.RECEPTIONIST
    )


def _with_availability(clinic: Clinic, doctor) -> None:
    with Session(bind=clinic.engine) as session:
        clinic.uow(session).availability.save(
            build_weekday_availability(clinic.tenant.id, doctor.id)
        )
        session.commit()


def _create(clinic: Clinic, doctor_id=None, start: datetime = SLOT) -> None:
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        uow = clinic.uow(session)
        CreateAppointment(uow, uow.code_generator(), FixedClock(BOOKING_CLOCK)).execute(
            _receptionist(clinic),
            CreateAppointmentCommand(
                patient_id=clinic.patient.id,
                doctor_id=doctor_id or clinic.doctor.id,
                location_id=clinic.tenant.primary_location.id,
                type=AppointmentType.CONSULT,
                scheduled_start=start,
                reason="Control",
            ),
        )


def _reschedule(clinic: Clinic, appointment_id, start: datetime = SLOT) -> None:
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        RescheduleAppointment(clinic.uow(session), FixedClock(BOOKING_CLOCK)).execute(
            _receptionist(clinic), appointment_id, start
        )


def _scheduled_at_11(clinic: Clinic) -> AppointmentId:
    appointment = copy.copy(clinic.appointment)
    appointment.id = AppointmentId.new()
    appointment.code = "A-2"
    appointment.scheduled_start = OTHER_SLOT
    appointment.status = "scheduled"
    with Session(bind=clinic.engine) as session:
        clinic.uow(session).appointments.save(appointment)
        session.commit()
    return appointment.id


def _outcomes(futures) -> list[str]:
    outcomes = []
    for future in futures:
        try:
            future.result(timeout=10)
            outcomes.append("booked")
        except SlotUnavailable as error:
            assert error.code == "slot.not_bookable"
            outcomes.append("refused")
    return sorted(outcomes)


def _blocked(futures) -> None:
    for future in futures:
        with pytest.raises(FutureTimeout):
            future.result(timeout=WAIT)


def _count_at(clinic: Clinic, start: datetime) -> int:
    with clinic.engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM appointments WHERE tenant_id = :t "
                "AND scheduled_start = :s AND status <> 'cancelled'"
            ),
            {"t": clinic.tenant.id.value, "s": start},
        ).scalar()


def test_two_simultaneous_bookings_of_one_slot_create_one(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        _with_availability(clinic, clinic.doctor)
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.lock_doctor_bookings(clinic.doctor.id)
            futures = [pool.submit(_create, clinic) for _ in range(2)]
            _blocked(futures)
            holder.rollback()
        finally:
            holder.close()

        assert _outcomes(futures) == ["booked", "refused"]
        assert _count_at(clinic, SLOT) == 1


def test_a_booking_and_a_reschedule_to_the_same_slot_leave_one(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        _with_availability(clinic, clinic.doctor)
        moved = _scheduled_at_11(clinic)
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.lock_doctor_bookings(clinic.doctor.id)
            futures = [pool.submit(_create, clinic), pool.submit(_reschedule, clinic, moved)]
            _blocked(futures)
            holder.rollback()
        finally:
            holder.close()

        assert _outcomes(futures) == ["booked", "refused"]
        assert _count_at(clinic, SLOT) == 1


def test_bookings_of_different_doctors_do_not_wait_on_each_other(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        _with_availability(clinic, clinic.doctor)
        other = build_user(clinic.tenant.id, Role.DOCTOR, email="other@csign.test")
        with Session(bind=engine) as session:
            clinic.uow(session).users.save(other)
            session.commit()
        _with_availability(clinic, other)

        holder = Session(bind=engine)
        try:
            clinic.uow(holder).appointments.lock_doctor_bookings(clinic.doctor.id)
            pool.submit(_create, clinic, other.id).result(timeout=5)
            holder.rollback()
        finally:
            holder.close()

        assert _count_at(clinic, SLOT) == 1
