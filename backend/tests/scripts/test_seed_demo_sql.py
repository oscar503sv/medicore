"""Explicitly opt-in: resets ONLY a disposable demo database, never DATABASE_URL by default.

Run with DEMO_TEST_DATABASE_URL pointing to a migrated, empty disposable PostgreSQL DB.
"""
from __future__ import annotations

import os
import random
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from medicore.application.common.context import ActorContext
from medicore.application.use_cases.subscriptions import GetMySubscription
from medicore.application.use_cases.users import InviteUser, InviteUserCommand
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import AnalyticsTier, ClinicalRecordType, Role, SealStatus
from medicore.domain.services.record_seal import verify_chain
from medicore.domain.services.seat_usage import SeatUsage
from medicore.domain.shared.errors import QuotaExceeded
from medicore.domain.shared.identifiers import RecordId, TenantId, UserId
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.database.tenant_purge import purge_tenants
from medicore.infrastructure.persistence.mappers.entities import to_medical_record
from medicore.infrastructure.persistence.models.application import ApplicationOrderModel
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.error_event import JobRunModel
from medicore.infrastructure.persistence.models.medical_document import MedicalDocumentModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.procedure import ProcedureModel
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.models.user import UserModel
from medicore.infrastructure.persistence.models.vaccination_record import VaccinationRecordModel
from medicore.infrastructure.persistence.repositories.diagnosis_catalog import (
    SqlDiagnosisCatalogRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from scripts import seed_demo as seed
from tests.support.builders import build_patient, build_tenant, build_user, soap_note
from tests.support.records import sealed


class DemoDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 15, 12, tzinfo=tz)


def test_three_clinics_seed_idempotence_and_nightly_reset(monkeypatch):
    url = os.environ.get("DEMO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set DEMO_TEST_DATABASE_URL to an empty disposable database")
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed, "get_session", factory)
    monkeypatch.setattr(seed, "get_session_factory", lambda: factory)
    monkeypatch.setattr(seed, "RNG", random.Random(42))
    monkeypatch.setattr(seed, "datetime", DemoDateTime)
    monkeypatch.setattr("sys.argv", ["seed_demo.py"])
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TenantModel)) == 0, (
            "This test requires an empty disposable database"
        )
        # Include every diagnosis used by the generators, without needing external files.
        repo = SqlDiagnosisCatalogRepository(session)
        for spec in seed.SPECIALTIES.values():
            for code, label in spec.diagnoses:
                repo.upsert(CatalogDiagnosis(version="cie11", code=code, label=label))
        untouched = build_tenant("clinica-loida")
        SqlTenantRepository(session).save(untouched)
        session.flush()
        real_record = sign_a_real_clinics_record(session, untouched)
        session.commit()
    try:
        seed.main()
        with factory() as session:
            before = assert_clinics(session)
        seed.main()  # existing tenants keep their activity
        with factory() as session:
            assert assert_clinics(session) == before
        monkeypatch.setattr("sys.argv", ["seed_demo.py", "--reset"])
        seed.main()
        with factory() as session:
            after = assert_clinics(session)
            assert all(after[slug][0] != before[slug][0] for slug in before)
            assert session.get(TenantModel, untouched.id.value).slug == "clinica-loida"
            # A real clinic's signed record is never reached by the demo reset.
            kept = SqlAlchemyUnitOfWork(session, untouched.id).medical_records
            assert verify_chain(kept.versions(real_record.id)) == (SealStatus.OK,)
            assert session.scalar(select(func.count()).select_from(MedicalRecordModel).where(
                MedicalRecordModel.tenant_id == untouched.id.value)) == 1
            assert triggers_are_always_enabled(session)
            demo_tenant = session.scalar(select(TenantModel).where(
                TenantModel.slug == seed.DEMO_CLINICS[0].slug))
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(delete(TenantModel).where(TenantModel.id == demo_tenant.id))
            job = session.scalar(select(JobRunModel).where(
                JobRunModel.job == "demo_reset").order_by(JobRunModel.finished_at.desc()))
            assert job.ok and job.detail == "clinica-demo, centro-norte, doc-demo"
    finally:
        with factory() as session:
            slugs = [d.slug for d in seed.DEMO_CLINICS] + ["clinica-loida"]
            purge_tenants(session, session.scalars(
                select(TenantModel.id).where(TenantModel.slug.in_(slugs))).all())
            session.commit()
        engine.dispose()


def sign_a_real_clinics_record(session: Session, tenant) -> MedicalRecord:
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@loida.test")
    patient = build_patient(tenant.id, code="P-00001")
    uow.users.save(doctor)
    uow.patients.save(patient)
    session.flush()
    when = datetime(2026, 11, 14, 9, tzinfo=UTC)
    record = sealed(MedicalRecord(
        id=RecordId.new(), tenant_id=tenant.id, code="REC-LOIDA-1", patient_id=patient.id,
        author_id=doctor.id, type=ClinicalRecordType.CONSULTATION, encounter_at=when,
        location_name="Sede", chief_complaint="Control", note=soap_note("s", "o", "a", "p"),
        vitals=Vitals(), signed_at=when, signed_by_id=doctor.id,
    ))
    uow.medical_records.save(record)
    session.flush()
    return record


def triggers_are_always_enabled(session: Session) -> bool:
    rows = session.execute(text(
        "SELECT tgenabled FROM pg_trigger WHERE tgname IN ("
        "'trg_medical_records_append_only', 'trg_medical_records_no_truncate', "
        "'trg_prescriptions_closing_only', 'trg_prescriptions_no_truncate')"
    )).scalars().all()
    return len(rows) == 4 and set(rows) == {"A"}


def assert_seals_verify(session: Session, tenant_id) -> None:
    """Every demo record, amendments included, checks out against its seal."""
    records = {
        row.id: to_medical_record(row) for row in session.scalars(
            select(MedicalRecordModel).where(MedicalRecordModel.tenant_id == tenant_id))
    }
    amended = {r.amends_record_id for r in records.values() if r.amends_record_id}
    assert records
    for last in (r for r in records.values() if r.id not in amended):
        chain = [last]
        while chain[0].amends_record_id:
            chain.insert(0, records[chain[0].amends_record_id.value])
        assert verify_chain(chain) == (SealStatus.OK,) * len(chain), last.code


def assert_clinics(session: Session) -> dict:
    result = {}
    for demo in seed.DEMO_CLINICS:
        row = session.scalar(select(TenantModel).where(TenantModel.slug == demo.slug))
        assert row is not None
        tenant_id = row.id
        tid = TenantId.parse(tenant_id)
        tenant = SqlTenantRepository(session).get_by_id(tid)
        assert tenant.legal_name == demo.legal_name
        assert tenant.primary_location.name == demo.location
        assert tenant.subscription == demo.subscription
        users = session.execute(select(UserModel.id, UserModel.email, UserModel.role).where(
            UserModel.tenant_id == tenant_id)).all()
        admin = next(u for u in users if u.email == f"admin@{demo.slug}.test")
        actor = ActorContext(user_id=UserId.parse(admin.id), tenant_id=tid, role=Role.ADMIN)
        clock = seed.SimClock(ZoneInfo(seed.TIMEZONE)).at(datetime(2026, 11, 15, 12))
        view = GetMySubscription(SqlAlchemyUnitOfWork(session, tid), clock).execute(actor)
        assert view.usage.doctors <= view.limits.doctors
        assert view.usage.support_users <= view.limits.support_users
        patients = session.execute(select(PatientModel.id, PatientModel.date_of_birth).where(
            PatientModel.tenant_id == tenant_id)).all()
        assert len(patients) == demo.patients.total
        appts = session.execute(select(AppointmentModel.patient_id, AppointmentModel.doctor_id,
            AppointmentModel.created_by_id, AppointmentModel.status).where(
            AppointmentModel.tenant_id == tenant_id)).all()
        assert appts
        result[demo.slug] = (tenant_id, len(appts), len(users))
        assert_seals_verify(session, tenant_id)
        assert triggers_are_always_enabled(session)
        documents = session.scalars(select(MedicalDocumentModel).where(
            MedicalDocumentModel.tenant_id == tenant_id)).all()
        for document in documents:
            assert document.storage_key == f"{tenant_id}/{document.patient_id}/{document.id}"
            if document.record_id is not None:
                record_patient = session.scalar(select(MedicalRecordModel.patient_id).where(
                    MedicalRecordModel.id == document.record_id,
                    MedicalRecordModel.tenant_id == tenant_id))
                assert record_patient == document.patient_id
        expected_emails = {f"{member[1]}@{demo.slug}.test" for member in demo.staff}
        expected_emails.add(f"admin@{demo.slug}.test")
        if demo.invited:
            expected_emails.add(f"{demo.invited[1]}@{demo.slug}.test")
        assert {u.email for u in users} == expected_emails
        if demo.slug == "doc-demo":
            assert view.plan.name == "Profesional independiente"
            assert view.usage == SeatUsage(1, 1)
            assert view.analytics_tier == AnalyticsTier.BASIC
            assert view.subscription.modules == frozenset()
            for model in (VaccinationRecordModel, ApplicationOrderModel, ProcedureModel):
                assert session.scalar(select(func.count()).select_from(model).where(
                    model.tenant_id == tenant_id)) == 0
            for role in (Role.DOCTOR, Role.NURSE, Role.RECEPTIONIST, Role.ADMIN):
                with pytest.raises(QuotaExceeded):
                    InviteUser(SqlAlchemyUnitOfWork(session, tid), seed.HASHER, clock).execute(
                        actor, InviteUserCommand("Extra User", f"extra-{role.value}@doc-demo.test",
                                                 role, "Temporary-Seed-9532"))
            doctor = next(u for u in users if u.role == Role.DOCTOR.value)
            reception = next(u for u in users if u.role == Role.RECEPTIONIST.value)
            today = DemoDateTime.now().date()
            children = {p.id for p in patients if (today - p.date_of_birth).days < 14 * 365.25}
            assert len(children) == demo.patients.children
            assert any(a.patient_id in children and a.status == "completed" for a in appts)
            assert all(a.doctor_id == doctor.id and a.created_by_id == reception.id for a in appts)
    return result
