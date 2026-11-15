from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.enums import DocumentKind
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import PatientId, RecordId, TenantId, UserId


def _register(tenant_id: TenantId, patient_id: PatientId) -> MedicalDocument:
    return MedicalDocument.register(
        tenant_id=tenant_id,
        patient_id=patient_id,
        file_name="analitica.pdf",
        kind=DocumentKind.LAB,
        mime_type="application/pdf",
        size_bytes=10,
        uploaded_by_id=UserId.new(),
        uploaded_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_register_builds_the_storage_key_from_tenant_patient_and_id():
    tenant_id, patient_id = TenantId.new(), PatientId.new()
    first = _register(tenant_id, patient_id)
    second = _register(tenant_id, patient_id)
    assert first.storage_key == f"{tenant_id}/{patient_id}/{first.id}"
    assert first.id != second.id
    assert first.storage_key != second.storage_key
    assert first.record_id is None


def test_link_to_a_record_of_the_same_patient():
    patient_id = PatientId.new()
    document = _register(TenantId.new(), patient_id)
    record = SimpleNamespace(id=RecordId.new(), patient_id=patient_id)
    document.link_to(record)
    assert document.record_id == record.id


def test_link_to_a_record_of_another_patient_is_rejected():
    document = _register(TenantId.new(), PatientId.new())
    record = SimpleNamespace(id=RecordId.new(), patient_id=PatientId.new())
    with pytest.raises(InvalidValueObject) as exc:
        document.link_to(record)
    assert exc.value.code == "document.record_mismatch"
    assert document.record_id is None
