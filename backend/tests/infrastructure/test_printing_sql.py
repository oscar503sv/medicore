"""Integration tests: what printing stores in PostgreSQL — certificates, exam orders, the
doctor's JVPM, the site's phone and the clinic's print settings (one outer transaction rolled
back at the end; SKIP when PostgreSQL is unreachable)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import CertificateKind, ClinicalRecordType, ExamKind, PaperSize, Role
from medicore.domain.shared.identifiers import CertificateId, RecordId, TenantId, UserId
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.print_settings import PrintSettings
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_analytics_sql import engine, session  # noqa: F401
from tests.support.builders import build_patient, build_tenant, build_user, soap_note

NOW = datetime(2026, 5, 20, 15, 0, tzinfo=UTC)


def test_round_trips(session):  # noqa: F811
    tenant = build_tenant(slug=f"test-print-{TenantId.new().value.hex[:8]}")
    tenant.print_settings = PrintSettings(PaperSize.LETTER, letterhead=True)
    tenant.primary_location.phone = "2222-3333"
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@print.test")
    doctor.jvpm = "12345"
    uow.users.save(doctor)
    patient = build_patient(tenant.id, code="P-00001")
    uow.patients.save(patient)
    session.flush()
    record = MedicalRecord(
        id=RecordId.new(), tenant_id=tenant.id, code="REC-1", patient_id=patient.id,
        author_id=doctor.id, type=ClinicalRecordType.CONSULTATION, encounter_at=NOW,
        location_name="Sede", chief_complaint="Control", note=soap_note(), vitals=Vitals(),
        signed_at=NOW, signed_by_id=doctor.id,
        exams=(ExamRequest("Ultrasonografía pélvica", ExamKind.IMAGING, "transvaginal"),),
    )
    uow.medical_records.save(record)
    session.flush()
    certificate = MedicalCertificate(
        id=CertificateId.new(), tenant_id=tenant.id, code="CM-2026-0001",
        patient_id=patient.id, record_id=record.id, doctor_id=doctor.id,
        kind=CertificateKind.REST, issued_at=NOW, rest_from=date(2026, 5, 20), rest_days=3,
        diagnosis="J06.9 IRA",
    )
    uow.certificates.save(certificate)
    session.flush()
    certificate.void(UserId.parse(doctor.id.value), "Error", NOW)
    uow.certificates.save(certificate)
    session.flush()
    session.expire_all()

    loaded_tenant = uow.tenants.get_by_id(tenant.id)
    assert loaded_tenant.print_settings == PrintSettings(PaperSize.LETTER, letterhead=True)
    assert loaded_tenant.primary_location.phone == "2222-3333"
    assert uow.users.get_by_id(doctor.id).jvpm == "12345"
    assert uow.medical_records.get_by_id(record.id).exams == record.exams
    loaded = uow.certificates.get_by_id(certificate.id)
    assert (loaded.kind, loaded.rest_until, loaded.diagnosis, loaded.void_reason) == (
        CertificateKind.REST, date(2026, 5, 22), "J06.9 IRA", "Error")
    assert [c.id for c in uow.certificates.list_by_patient(patient.id)] == [certificate.id]
    assert [c.id for c in uow.certificates.list_by_record(record.id)] == [certificate.id]
