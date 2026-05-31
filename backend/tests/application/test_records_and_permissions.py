"""Tests for records (amend, view permissions), patients, and multi-tenant isolation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from medicore.application.common.context import ActorContext
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
)
from medicore.domain.enums import AppointmentType, RecordStatus, Sex
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import build_tenant, build_user, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)


def _sign_a_record(seed, uow):
    create = CreateAppointment(uow, SequentialCodeGenerator(), FixedClock())
    appt = create.execute(
        seed.doctor_actor,
        CreateAppointmentCommand(
            patient_id=seed.patient.id,
            doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id,
            type=AppointmentType.CONSULT,
            scheduled_start=MONDAY_9AM,
            duration_minutes=30,
            reason="Control",
        ),
    )
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor,
        consultation.id,
        ConsultationPatch(
            soap=SoapNote("s", "o", "a", "p"), vitals=Vitals(heart_rate=70, weight=Decimal("68"))
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


class TestRecordPermissions:
    def test_receptionist_cannot_view_records(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ListMedicalRecords(uow).execute(seed.receptionist_actor)

    def test_doctor_can_view_records(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        _sign_a_record(seed, uow)
        records = ListMedicalRecords(uow).execute(seed.doctor_actor)
        assert len(records) == 1

    def test_get_record_is_audited(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)
        GetMedicalRecord(uow, FixedClock()).execute(seed.doctor_actor, record.id)
        assert uow.audit.query(action="record.viewed")


class TestAmendment:
    def test_amend_creates_linked_version_without_mutating_original(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)

        amendment = AmendMedicalRecord(uow, FixedClock()).execute(
            seed.doctor_actor, original.id, chief_complaint="Corregido"
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
                seed.actor(seed.nurse), original.id, chief_complaint="x"
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
