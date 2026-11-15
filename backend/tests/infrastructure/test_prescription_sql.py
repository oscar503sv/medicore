"""Integration tests: prescriptions against PostgreSQL (closing fields, the CHECK, the lock).

The concurrent test uses committed rows (the ``Clinic`` harness of the consultation sign
tests); the others run in a rolled-back transaction. Skipped when PostgreSQL is unreachable.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from medicore.application.use_cases.prescriptions import (
    CancelPrescription,
    CompletePrescription,
)
from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.shared.errors import InvalidStateTransition
from medicore.domain.shared.identifiers import PrescriptionId
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_consultation_sign_sql import (  # noqa: F401
    NOW,
    WAIT,
    Clinic,
    clinic_session,
    engine,
)
from tests.support.fakes import FixedClock

REASON = "Patient developed a rash after the first doses"


def _prescription(clinic) -> Prescription:
    return Prescription(
        id=PrescriptionId.new(), tenant_id=clinic.tenant.id, patient_id=clinic.patient.id,
        prescriber_id=clinic.doctor.id, drug="Enalapril", dose="20 mg", schedule="1x",
        start_date=date(2026, 6, 1),
    )


def _prepare(clinic_session):  # noqa: F811
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    uow.users.save(clinic.doctor)
    uow.patients.save(clinic.patient)
    session.flush()
    return clinic, session, uow


def test_closing_fields_round_trip(clinic_session):  # noqa: F811
    clinic, session, uow = _prepare(clinic_session)
    rx = _prescription(clinic)
    rx.cancel(clinic.doctor.id, REASON, NOW)
    uow.prescriptions.save(rx)
    session.flush()
    session.expire_all()

    saved = uow.prescriptions.get_by_id(rx.id)

    assert saved.status == PrescriptionStatus.CANCELLED
    assert (saved.cancel_reason, saved.closed_at, saved.closed_by_id) == (
        REASON, NOW, clinic.doctor.id)


def test_the_check_refuses_a_cancelled_prescription_without_a_reason(clinic_session):  # noqa: F811
    clinic, session, uow = _prepare(clinic_session)
    rx = _prescription(clinic)
    rx.status = PrescriptionStatus.CANCELLED

    with pytest.raises(IntegrityError), session.begin_nested():
        uow.prescriptions.save(rx)
        session.flush()


def test_concurrent_complete_and_cancel_close_it_once(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        rx = _prescription(clinic)
        with Session(bind=engine) as session:
            clinic.uow(session).prescriptions.save(rx)
            session.commit()

        def complete() -> str:
            with Session(bind=engine, expire_on_commit=False) as session:
                CompletePrescription(clinic.uow(session), FixedClock(NOW)).execute(
                    clinic.actor, rx.id
                )
            return "completed"

        def cancel() -> str:
            with Session(bind=engine, expire_on_commit=False) as session:
                CancelPrescription(clinic.uow(session), FixedClock(NOW)).execute(
                    clinic.actor, rx.id, reason=REASON
                )
            return "cancelled"

        holder = Session(bind=engine)
        try:
            clinic.uow(holder).prescriptions.get_for_update(rx.id)
            futures = [pool.submit(complete), pool.submit(cancel)]
            for future in futures:
                with pytest.raises(FutureTimeout):
                    future.result(timeout=WAIT)
            holder.rollback()
        finally:
            holder.close()

        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except InvalidStateTransition:
                outcomes.append("refused")

        assert sorted(outcomes) in (["completed", "refused"], ["cancelled", "refused"])
        assert clinic.scalar(
            "SELECT count(*) FROM audit_logs WHERE tenant_id = :t "
            "AND action IN ('prescription.completed', 'prescription.cancelled')"
        ) == 1
