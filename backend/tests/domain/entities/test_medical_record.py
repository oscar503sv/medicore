"""Tests for MedicalRecord immutability and amendments."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from medicore.domain.entities.medical_record import (
    AMENDMENT_REASON_MAX,
    AMENDMENT_REASON_MIN,
    MedicalRecord,
)
from medicore.domain.enums import ClinicalRecordType, RecordStatus
from medicore.domain.shared.errors import InvalidValueObject, PermissionDenied, RecordAlreadySigned
from medicore.domain.shared.identifiers import (
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import soap_note


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
        note=soap_note("s", "o", "a", "p"),
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


REASON = "Se corrige el motivo de consulta"


def amend(record: MedicalRecord, **overrides) -> MedicalRecord:
    args = dict(
        by=record.author_id, new_id=RecordId.new(), signed_at=datetime(2026, 5, 13, 10, 0),
        reason=REASON, chief_complaint="Cefalea (corregido)",
    )
    return record.amend(**{**args, **overrides})


class TestAmendment:
    def test_amend_creates_new_linked_version(self):
        original = make_record()
        amended = amend(original)
        assert amended.id != original.id
        assert amended.status == RecordStatus.AMENDED
        assert amended.amends_record_id == original.id
        assert amended.is_amendment
        assert amended.chief_complaint == "Cefalea (corregido)"
        assert amended.amendment_reason == REASON
        assert amended.signed_at == datetime(2026, 5, 13, 10, 0)

    def test_the_author_stays_and_signs_the_version(self):
        original = make_record()
        amended = amend(original)
        assert amended.author_id == original.author_id
        assert amended.signed_by_id == original.author_id

    def test_amend_does_not_mutate_original(self):
        original = make_record()
        amend(original, chief_complaint="x")
        assert original.chief_complaint == "Cefalea"
        assert original.status == RecordStatus.SIGNED
        assert not original.is_amendment
        assert original.amendment_reason is None

    def test_the_reason_is_trimmed(self):
        assert amend(make_record(), reason=f"  {REASON}  ").amendment_reason == REASON

    def test_only_the_author_amends(self):
        with pytest.raises(PermissionDenied) as exc:
            amend(make_record(), by=UserId.new())
        assert exc.value.code == "record.not_own"

    @pytest.mark.parametrize("reason", ["", "   ", "corto", "x" * 9, "y" * 1001])
    def test_the_reason_must_fit_its_bounds(self, reason):
        with pytest.raises(InvalidValueObject) as exc:
            amend(make_record(), reason=reason)
        assert exc.value.code == "record.amend_reason_invalid"
        assert exc.value.params == {"min": AMENDMENT_REASON_MIN, "max": AMENDMENT_REASON_MAX}

    def test_the_reason_bounds_are_inclusive(self):
        assert amend(make_record(), reason="x" * AMENDMENT_REASON_MIN)
        assert amend(make_record(), reason="x" * AMENDMENT_REASON_MAX)

    def test_an_amendment_must_change_something(self):
        original = make_record()
        for kwargs in (
            {"chief_complaint": None},
            {"chief_complaint": "Cefalea"},
            {"chief_complaint": "  Cefalea  "},
            {"chief_complaint": None, "note": original.note},
            {"chief_complaint": None, "note": original.note.with_texts({"plan": " p "})},
        ):
            with pytest.raises(InvalidValueObject) as exc:
                amend(original, **kwargs)
            assert exc.value.code == "record.amend_empty"

    def test_a_note_change_alone_is_enough(self):
        original = make_record()
        amended = amend(
            original, chief_complaint=None, note=original.note.with_texts({"plan": "nuevo"})
        )
        assert amended.note.texts()["plan"] == "nuevo"
        assert amended.chief_complaint == "Cefalea"

    def test_the_author_is_checked_before_the_reason(self):
        with pytest.raises(PermissionDenied):
            amend(make_record(), by=UserId.new(), reason="")

    def test_the_chain_keeps_its_author(self):
        first = amend(make_record())
        second = amend(first, chief_complaint="Cefalea (otra vez)")
        assert second.amends_record_id == first.id
        assert second.author_id == first.author_id
        with pytest.raises(PermissionDenied):
            amend(first, by=UserId.new())

    def test_a_record_that_is_not_signed_cannot_be_amended(self):
        draft = dataclasses.replace(make_record(), status=RecordStatus.DRAFT)
        with pytest.raises(RecordAlreadySigned) as exc:
            amend(draft)
        assert exc.value.code == "record.not_amendable"
