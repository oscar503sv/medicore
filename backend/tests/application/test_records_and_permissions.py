"""Tests for records (amend, view permissions), patients, and multi-tenant isolation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AutosaveConsultation,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.patients import (
    CreatePatient,
    CreatePatientCommand,
    GetPatientDetail,
    ListPatients,
)
from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    ListMedicalRecords,
    RecordQuery,
    UploadDocument,
    UploadDocumentCommand,
)
from medicore.domain.enums import AppointmentType, DocumentKind, RecordStatus, Sex
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.errors import InvalidValueObject, PermissionDenied
from medicore.domain.shared.identifiers import PatientId, RecordId
from medicore.domain.value_objects.icd_code import IcdCode
from tests.support.builders import (
    build_patient,
    build_tenant,
    build_user,
    seed_clinic,
    soap_note,
)
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)


def _sign_a_record(seed, uow, patient=None, start=MONDAY_9AM):
    patient = patient or seed.patient
    create = CreateAppointment(uow, SequentialCodeGenerator(), FixedClock())
    appt = create.execute(
        seed.doctor_actor,
        CreateAppointmentCommand(
            patient_id=patient.id,
            doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id,
            type=AppointmentType.CONSULT,
            scheduled_start=start,
            reason="Control",
        ),
    )
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor,
        consultation.id,
        ConsultationPatch(
            note=soap_note("s", "o", "a", "p").texts(),
            vitals={"heart_rate": 70, "weight": Decimal("68")},
        ),
    )
    AddDiagnosis(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, IcdCode("I10", "HTA")
    )
    return SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id)
    )


class TestPatients:
    def test_create_patient_gets_code(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        patient = CreatePatient(uow, SequentialCodeGenerator(), FixedClock()).execute(
            seed.receptionist_actor,
            CreatePatientCommand(
                first_name="Marc",
                last_name="Soler",
                sex=Sex.MALE,
                date_of_birth=datetime(1990, 1, 1).date(),
            ),
        )
        assert patient.code == "P-00142"
        assert uow.audit.query(action="patient.created")

    def test_patient_detail_derives_counts(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        _sign_a_record(seed, uow)
        detail = GetPatientDetail(uow, FixedClock()).execute(seed.doctor_actor, seed.patient.id)
        assert detail.records_count == 1
        assert detail.active_prescriptions == 0
        assert detail.last_visit == MONDAY_9AM

    def test_patient_detail_audits_chart_view_once_per_access(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        detail = GetPatientDetail(uow, FixedClock())
        detail.execute(seed.doctor_actor, seed.patient.id)
        assert len(uow.audit.query(action="patient.chart_viewed")) == 1
        detail.execute(seed.doctor_actor, seed.patient.id)
        assert len(uow.audit.query(action="patient.chart_viewed")) == 2


class TestRecordPermissions:
    def test_receptionist_cannot_view_records(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ListMedicalRecords(uow, FixedClock()).execute(
                seed.receptionist_actor, RecordQuery(), Paging()
            )

    def test_doctor_can_view_records(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        _sign_a_record(seed, uow)
        page = ListMedicalRecords(uow, FixedClock()).execute(
            seed.doctor_actor, RecordQuery(), Paging()
        )
        assert len(page.items) == 1

    def test_only_a_doctor_opens_the_clinical_content(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)
        get = GetMedicalRecord(uow, FixedClock())
        assert get.execute(seed.doctor_actor, record.id).record.id == record.id
        for actor in (
            seed.actor(seed.admin), seed.actor(seed.nurse), seed.receptionist_actor,
            replace(seed.actor(seed.admin), impersonated_by=seed.platform_admin.id),
        ):
            with pytest.raises(PermissionDenied) as exc:
                get.execute(actor, record.id)
            assert exc.value.code == "permission.missing"

    def test_get_record_is_audited(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)
        GetMedicalRecord(uow, FixedClock()).execute(seed.doctor_actor, record.id)
        assert uow.audit.query(action="record.viewed")


def _upload_cmd(seed, **overrides) -> UploadDocumentCommand:
    defaults = dict(
        patient_id=seed.patient.id,
        file_name="analitica.pdf",
        kind=DocumentKind.LAB,
        mime_type="application/pdf",
        size_bytes=1024,
    )
    defaults.update(overrides)
    return UploadDocumentCommand(**defaults)


class TestUploadDocument:
    def test_upload_persists_document_and_audits(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        document = UploadDocument(uow, FixedClock()).execute(seed.doctor_actor, _upload_cmd(seed))
        assert uow.documents.list_by_patient(seed.patient.id) == [document]
        assert uow.audit.query(action="document.uploaded")

    def test_unknown_patient_is_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(EntityNotFound):
            UploadDocument(uow, FixedClock()).execute(
                seed.doctor_actor, _upload_cmd(seed, patient_id=PatientId.new())
            )

    def test_disallowed_mime_type_is_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(ValidationError):
            UploadDocument(uow, FixedClock()).execute(
                seed.doctor_actor, _upload_cmd(seed, mime_type="application/x-msdownload")
            )

    def test_size_out_of_bounds_is_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        for size in (0, -1, 26 * 1024 * 1024):
            with pytest.raises(ValidationError):
                UploadDocument(uow, FixedClock()).execute(
                    seed.doctor_actor, _upload_cmd(seed, size_bytes=size)
                )

    def test_traversal_file_name_is_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        for name in ("../../etc/passwd", "a/b.pdf", "", "x" * 256):
            with pytest.raises(ValidationError):
                UploadDocument(uow, FixedClock()).execute(
                    seed.doctor_actor, _upload_cmd(seed, file_name=name)
                )

    def test_the_server_chooses_the_storage_key(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        upload = UploadDocument(uow, FixedClock())
        first = upload.execute(seed.doctor_actor, _upload_cmd(seed))
        second = upload.execute(seed.doctor_actor, _upload_cmd(seed))
        assert first.storage_key == f"{seed.tenant.id}/{seed.patient.id}/{first.id}"
        assert first.storage_key != second.storage_key

    def test_file_name_is_stored_trimmed(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        document = UploadDocument(uow, FixedClock()).execute(
            seed.doctor_actor, _upload_cmd(seed, file_name="  analitica.pdf  ")
        )
        assert document.file_name == "analitica.pdf"

    def test_document_links_to_a_record_of_the_same_patient(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)
        document = UploadDocument(uow, FixedClock()).execute(
            seed.doctor_actor, _upload_cmd(seed, record_id=record.id)
        )
        assert document.record_id == record.id

    def test_an_old_version_links_to_the_current_one(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)
        amendment = AmendMedicalRecord(uow, FixedClock()).execute(
            seed.doctor_actor, original.id, reason="Se corrige el motivo", chief_complaint="X"
        )
        document = UploadDocument(uow, FixedClock()).execute(
            seed.doctor_actor, _upload_cmd(seed, record_id=original.id)
        )
        assert document.record_id == amendment.id

    def test_record_of_another_patient_is_rejected_and_leaves_no_trace(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        other = build_patient(seed.tenant.id, code="P-00200", primary_doctor_id=seed.doctor.id)
        seed.factory.store.patients[other.id.value] = other
        record = _sign_a_record(seed, uow, patient=other, start=MONDAY_9AM + timedelta(hours=2))
        audits = len(uow.audit.query(action="document.uploaded"))
        notifications = len(seed.factory.store.notifications)
        with pytest.raises(InvalidValueObject) as exc:
            UploadDocument(uow, FixedClock()).execute(
                seed.doctor_actor, _upload_cmd(seed, record_id=record.id)
            )
        assert exc.value.code == "document.record_mismatch"
        assert uow.documents.list_by_patient(seed.patient.id) == []
        assert len(uow.audit.query(action="document.uploaded")) == audits
        assert len(seed.factory.store.notifications) == notifications

    def test_unknown_record_is_not_found(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(EntityNotFound):
            UploadDocument(uow, FixedClock()).execute(
                seed.doctor_actor, _upload_cmd(seed, record_id=RecordId.new())
            )

    def test_record_of_another_clinic_is_not_found(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)
        other_tenant = build_tenant(slug="otra-clinica")
        other_admin = build_user(other_tenant.id, role=seed.admin.role)
        other_patient = build_patient(other_tenant.id)
        store = seed.factory.store
        store.tenants[other_tenant.id.value] = other_tenant
        store.users[other_admin.id.value] = other_admin
        store.patients[other_patient.id.value] = other_patient
        actor = ActorContext(
            user_id=other_admin.id, tenant_id=other_tenant.id, role=other_admin.role
        )
        with pytest.raises(EntityNotFound):
            UploadDocument(seed.factory.for_tenant(other_tenant.id), FixedClock()).execute(
                actor, _upload_cmd(seed, patient_id=other_patient.id, record_id=record.id)
            )

    def test_support_sessions_cannot_upload(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        support = replace(seed.actor(seed.admin), impersonated_by=seed.platform_admin.id)
        with pytest.raises(PermissionDenied) as exc:
            UploadDocument(uow, FixedClock()).execute(support, _upload_cmd(seed))
        assert exc.value.code == "support.clinical_forbidden"
        assert uow.documents.list_by_patient(seed.patient.id) == []


class TestAmendment:
    def test_amend_creates_linked_version_without_mutating_original(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)

        amendment = AmendMedicalRecord(uow, FixedClock()).execute(
            seed.doctor_actor, original.id,
            reason="Se corrige el motivo", chief_complaint="Corregido",
        )

        assert amendment.status == RecordStatus.AMENDED
        assert amendment.amends_record_id == original.id
        assert amendment.chief_complaint == "Corregido"
        # original untouched
        stored_original = uow.medical_records.get_by_id(original.id)
        assert stored_original.status == RecordStatus.SIGNED
        assert stored_original.chief_complaint != "Corregido"
        assert uow.audit.query(action="record.amended")

    def test_nurse_cannot_amend(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)
        with pytest.raises(PermissionDenied):
            AmendMedicalRecord(uow, FixedClock()).execute(
                seed.actor(seed.nurse), original.id, reason="Una razón válida", chief_complaint="x"
            )


class TestMultiTenantIsolation:
    def test_repositories_do_not_leak_across_tenants(self):
        seed = seed_clinic()
        # A second tenant sharing the same store, with its own patient.
        other_tenant = build_tenant(slug="otra-clinica")
        other_admin = build_user(other_tenant.id, role=seed.admin.role)
        store = seed.factory.store
        store.tenants[other_tenant.id.value] = other_tenant
        store.users[other_admin.id.value] = other_admin

        # Tenant A lists patients → only sees its own seeded patient.
        uow_a = seed.factory.for_tenant(seed.tenant.id)
        page_a = ListPatients(uow_a).execute(seed.doctor_actor)
        assert all(p.tenant_id == seed.tenant.id for p in page_a.items)
        assert seed.patient.id in {p.id for p in page_a.items}

        # Tenant B sees none of tenant A's patients.
        uow_b = seed.factory.for_tenant(other_tenant.id)
        actor_b = ActorContext(
            user_id=other_admin.id, tenant_id=other_tenant.id, role=other_admin.role
        )
        page_b = ListPatients(uow_b).execute(actor_b)
        assert page_b.total == 0
