"""Integration tests: amendments against PostgreSQL (the chain, its lock and its constraints).

Concurrent tests use committed rows (the ``Clinic`` harness of the consultation sign tests);
the constraint and read tests run in a rolled-back transaction. Skipped when PostgreSQL is
unreachable.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from medicore.application.use_cases.records import AmendMedicalRecord
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import CertificateKind
from medicore.domain.shared.errors import RecordSuperseded
from medicore.domain.shared.identifiers import CertificateId, RecordId
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_consultation_sign_sql import (  # noqa: F401
    NOW,
    WAIT,
    Clinic,
    _record,
    _save_the_booking,
    clinic_session,
    engine,
)
from tests.support.fakes import FixedClock

REASON = "Se corrige el motivo de consulta"


def _amendment(clinic, original: MedicalRecord, reason: str | None = REASON) -> MedicalRecord:
    amended = _record(clinic, original.consultation_id, amends=original.id, previous=original)
    object.__setattr__(amended, "amendment_reason", reason)
    return amended


def _prepare(clinic_session):  # noqa: F811
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    consultation_id = _save_the_booking(uow, session, clinic)
    original = _record(clinic, consultation_id)
    uow.medical_records.save(original)
    session.flush()
    return clinic, session, uow, original


def test_concurrent_amends_store_one_version(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
        clinic.sign()
        record_id = RecordId.parse(
            clinic.scalar("SELECT id FROM medical_records WHERE tenant_id = :t")
        )

        def amend() -> str:
            with Session(bind=engine, expire_on_commit=False) as session:
                uow = clinic.uow(session)
                AmendMedicalRecord(uow, FixedClock(NOW)).execute(
                    clinic.actor, record_id, reason=REASON, chief_complaint="Corregido"
                )
            return "amended"

        holder = Session(bind=engine)
        try:
            clinic.uow(holder).medical_records.get_for_update(record_id)
            futures = [pool.submit(amend) for _ in range(2)]
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
            except RecordSuperseded:
                outcomes.append("refused")

        assert sorted(outcomes) == ["amended", "refused"]
        assert clinic.scalar(
            "SELECT count(*) FROM medical_records "
            "WHERE tenant_id = :t AND amends_record_id IS NOT NULL"
        ) == 1


def test_the_record_lock_does_not_block_certificate_inserts(engine):  # noqa: F811
    with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
        clinic.sign()
        record_id = RecordId.parse(
            clinic.scalar("SELECT id FROM medical_records WHERE tenant_id = :t")
        )
        holder = Session(bind=engine)
        try:
            clinic.uow(holder).medical_records.get_for_update(record_id)

            def issue() -> None:
                with Session(bind=engine) as session:
                    clinic.uow(session).certificates.save(
                        MedicalCertificate(
                            id=CertificateId.new(), tenant_id=clinic.tenant.id,
                            code=f"CM-{uuid.uuid4().hex[:8]}", patient_id=clinic.patient.id,
                            record_id=record_id, doctor_id=clinic.doctor.id,
                            kind=CertificateKind.REST, issued_at=NOW,
                            rest_from=date(2026, 6, 1), rest_days=2,
                        )
                    )
                    session.commit()

            # A plain FOR UPDATE would hold this insert back (its FK check takes FOR KEY SHARE).
            pool.submit(issue).result(timeout=5)
        finally:
            holder.rollback()
            holder.close()


def test_the_index_refuses_a_second_amendment_of_the_same_record(clinic_session):  # noqa: F811
    clinic, session, uow, original = _prepare(clinic_session)
    uow.medical_records.save(_amendment(clinic, original))
    session.flush()

    with pytest.raises(IntegrityError), session.begin_nested():
        uow.medical_records.save(_amendment(clinic, original))
        session.flush()


def test_the_check_refuses_an_amendment_without_a_reason(clinic_session):  # noqa: F811
    clinic, session, uow, original = _prepare(clinic_session)

    with pytest.raises(IntegrityError), session.begin_nested():
        uow.medical_records.save(_amendment(clinic, original, reason=None))
        session.flush()


def test_the_reason_round_trips_and_originals_have_none(clinic_session):  # noqa: F811
    clinic, session, uow, original = _prepare(clinic_session)
    amended = _amendment(clinic, original)
    uow.medical_records.save(amended)
    session.flush()
    session.expire_all()

    assert uow.medical_records.get_by_id(amended.id).amendment_reason == REASON
    assert uow.medical_records.get_by_id(original.id).amendment_reason is None


def test_versions_and_successor_follow_the_chain(clinic_session):  # noqa: F811
    clinic, session, uow, original = _prepare(clinic_session)
    first = _amendment(clinic, original)
    uow.medical_records.save(first)
    second = _amendment(clinic, first)
    uow.medical_records.save(second)
    unrelated = _record(clinic, None)
    uow.medical_records.save(unrelated)
    session.flush()

    expected = [original.id, first.id, second.id]
    for start in expected:
        assert [r.id for r in uow.medical_records.versions(start)] == expected
    assert [r.id for r in uow.medical_records.versions(unrelated.id)] == [unrelated.id]
    assert uow.medical_records.versions(RecordId.new()) == []
    assert uow.medical_records.successor_id(original.id) == first.id
    assert uow.medical_records.successor_id(first.id) == second.id
    assert uow.medical_records.successor_id(second.id) is None
    assert uow.medical_records.successor_id(unrelated.id) is None


def test_lists_and_summaries_leave_out_replaced_records(clinic_session):  # noqa: F811
    from medicore.domain.repositories._support import Paging, RecordFilter

    clinic, session, uow, original = _prepare(clinic_session)
    first = _amendment(clinic, original)
    uow.medical_records.save(first)
    other = _record(clinic, None)
    uow.medical_records.save(other)
    session.flush()

    current = {first.id, other.id}
    assert {r.id for r in uow.medical_records.list_by_patient(clinic.patient.id)} == current
    page = uow.medical_records.summaries(RecordFilter(), Paging())
    assert {s.id for s in page.items} == {str(i) for i in current}
    assert page.total == 2
