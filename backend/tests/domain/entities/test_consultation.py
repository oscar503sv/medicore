"""Tests for Consultation editing, completion and signing."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import (
    ClinicalRecordType,
    ConsultationStatus,
    PrescriptionStatus,
    RecordStatus,
)
from medicore.domain.shared.errors import ConsultationNotSignable
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals


def make_consultation() -> Consultation:
    return Consultation(
        id=ConsultationId.new(),
        tenant_id=TenantId.new(),
        appointment_id=AppointmentId.new(),
        patient_id=PatientId.new(),
        doctor_id=UserId.new(),
        started_at=datetime(2026, 5, 12, 9, 0),
    )


def fill_for_signing(c: Consultation) -> None:
    c.autosave(
        soap=SoapNote("s", "o", "a", "p"),
        vitals=Vitals(heart_rate=72, weight=Decimal("70")),
    )
    c.add_diagnosis(IcdCode("I10", "Hipertensión"))


class TestCompletion:
    def test_empty_is_zero(self):
        assert make_consultation().compute_completion() == 0

    def test_full_is_hundred(self):
        c = make_consultation()
        fill_for_signing(c)
        assert c.compute_completion() == 100

    def test_partial_below_threshold(self):
        c = make_consultation()
        c.autosave(soap=SoapNote(subjective="only subjective"))
        # 1/4 SOAP = 15%, no dx, no vitals
        assert c.compute_completion() == 15


class TestEditingGuards:
    def test_dedup_diagnosis(self):
        c = make_consultation()
        c.add_diagnosis(IcdCode("I10", "HTA"))
        c.add_diagnosis(IcdCode("I10", "HTA"))
        assert len(c.diagnoses) == 1

    def test_remove_diagnosis(self):
        c = make_consultation()
        c.add_diagnosis(IcdCode("I10", "HTA"))
        c.remove_diagnosis("i10")
        assert c.diagnoses == []


class TestSigning:
    def test_blocks_when_incomplete(self):
        c = make_consultation()
        c.autosave(soap=SoapNote(subjective="x"))
        with pytest.raises(ConsultationNotSignable):
            c.sign(
                record_id=RecordId.new(),
                record_code="REC-2026-0512-EV",
                record_type=ClinicalRecordType.CONSULTATION,
                location_name="Madrid",
                chief_complaint="x",
                signed_by_id=c.doctor_id,
            )

    def test_sign_emits_record_and_prescriptions(self):
        c = make_consultation()
        fill_for_signing(c)
        c.add_prescription_draft(
            PrescriptionDraft(drug="Enalapril", dose="20 mg", schedule="1× día", duration_days=30)
        )

        result = c.sign(
            record_id=RecordId.new(),
            record_code="REC-2026-0512-EV",
            record_type=ClinicalRecordType.CONSULTATION,
            location_name="Madrid · Atocha",
            chief_complaint="Control HTA",
            signed_by_id=c.doctor_id,
        )

        assert c.status == ConsultationStatus.SIGNED
        assert c.ended_at is not None
        assert result.record.status == RecordStatus.SIGNED
        assert result.record.consultation_id == c.id
        assert len(result.record.diagnoses) == 1
        assert len(result.prescriptions) == 1

        rx = result.prescriptions[0]
        assert rx.drug == "Enalapril"
        assert rx.status == PrescriptionStatus.ACTIVE
        assert rx.record_id == result.record.id
        assert rx.end_date is not None  # derived from duration_days
        # snapshot embedded in the immutable record
        assert result.record.prescriptions[0].drug == "Enalapril"

    def test_cannot_edit_after_signing(self):
        c = make_consultation()
        fill_for_signing(c)
        c.sign(
            record_id=RecordId.new(),
            record_code="REC-2026-0512-EV",
            record_type=ClinicalRecordType.CONSULTATION,
            location_name="Madrid",
            chief_complaint="x",
            signed_by_id=c.doctor_id,
        )
        with pytest.raises(ConsultationNotSignable):
            c.add_diagnosis(IcdCode("E11.9", "Diabetes"))
