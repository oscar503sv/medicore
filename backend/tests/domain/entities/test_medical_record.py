"""Tests for MedicalRecord immutability and amendments."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import ClinicalRecordType, RecordStatus
from medicore.domain.shared.identifiers import (
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals


def make_record() -> MedicalRecord:
    return MedicalRecord(
        id=RecordId.new(),
        tenant_id=TenantId.new(),
        code="REC-2026-0512-CR",
        patient_id=PatientId.new(),
        author_id=UserId.new(),
        type=ClinicalRecordType.CONSULTATION,
        encounter_at=datetime(2026, 5, 12, 9, 0),
        location_name="Madrid · Atocha",
        chief_complaint="Cefalea",
        soap=SoapNote("s", "o", "a", "p"),
        vitals=Vitals(),
        signed_at=datetime(2026, 5, 12, 9, 30),
        signed_by_id=UserId.new(),
        diagnoses=[IcdCode("I10", "Hipertensión")],
    )


class TestMedicalRecordImmutability:
    def test_signed_by_default(self):
        assert make_record().status == RecordStatus.SIGNED

    def test_fields_are_frozen(self):
        record = make_record()
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.chief_complaint = "otra cosa"  # type: ignore[misc]

    def test_lists_normalized_to_tuples(self):
        record = make_record()
        assert isinstance(record.diagnoses, tuple)


class TestAmendment:
    def test_amend_creates_new_linked_version(self):
        original = make_record()
        amended = original.amend(
            new_id=RecordId.new(),
            author_id=UserId.new(),
            chief_complaint="Cefalea (corregido)",
        )
        assert amended.id != original.id
        assert amended.status == RecordStatus.AMENDED
        assert amended.amends_record_id == original.id
        assert amended.is_amendment
        assert amended.chief_complaint == "Cefalea (corregido)"

    def test_amend_does_not_mutate_original(self):
        original = make_record()
        original.amend(new_id=RecordId.new(), author_id=UserId.new(), chief_complaint="x")
        assert original.chief_complaint == "Cefalea"
        assert original.status == RecordStatus.SIGNED
        assert not original.is_amendment
