"""Integration tests: clinical notes and note settings in PostgreSQL (one outer transaction
rolled back at the end; SKIP when PostgreSQL is unreachable)."""

from __future__ import annotations

from datetime import UTC, datetime

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import ClinicalRecordType, Role
from medicore.domain.services.note_templates import HISTORY
from medicore.domain.shared.identifiers import RecordId, TenantId
from medicore.domain.value_objects.clinical_note import ClinicalNote
from medicore.domain.value_objects.note_settings import NoteSettings
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_analytics_sql import engine, session  # noqa: F401
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 5, 20, 15, 0, tzinfo=UTC)


def test_round_trips(session):  # noqa: F811
    tenant = build_tenant(slug=f"test-notes-{TenantId.new().value.hex[:8]}")
    settings = NoteSettings(enabled=("soap", "history"), default="soap",
                            rules={"first_visit": "history"}, locked=True)
    tenant.note_settings = settings
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@notes.test")
    doctor.set_note_template("history")
    uow.users.save(doctor)
    patient = build_patient(tenant.id, code="P-00001")
    uow.patients.save(patient)
    session.flush()
    note = ClinicalNote.blank(HISTORY).with_texts({"anamnesis": "Cefalea", "treatment": "AINE"})
    record = MedicalRecord(
        id=RecordId.new(), tenant_id=tenant.id, code="REC-1", patient_id=patient.id,
        author_id=doctor.id, type=ClinicalRecordType.CONSULTATION, encounter_at=NOW,
        location_name="Sede", chief_complaint="Control", note=note, vitals=Vitals(),
        signed_at=NOW, signed_by_id=doctor.id,
    )
    uow.medical_records.save(record)
    session.flush()
    session.expire_all()

    assert uow.tenants.get_by_id(tenant.id).note_settings == settings
    assert uow.users.get_by_id(doctor.id).preferences.note_template == "history"
    assert uow.medical_records.get_by_id(record.id).note == note
