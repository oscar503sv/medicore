"""Tests for Consultation editing, completion and signing."""

from __future__ import annotations

from dataclasses import replace
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
    SealStatus,
)
from medicore.domain.services.record_seal import compute_seal, verify_chain
from medicore.domain.shared.errors import (
    ConsultationAlreadySigned,
    ConsultationNotSignable,
    InvalidValueObject,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from tests.support.builders import soap_note


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
        note=soap_note("s", "o", "a", "p").texts(),
        vitals={"heart_rate": 72, "weight": Decimal("70")},
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
        c.autosave(note={"subjective": "only subjective"})
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
    def test_signing_twice_raises_already_signed(self):
        c = make_consultation()
        fill_for_signing(c)
        kwargs = dict(
            record_id=RecordId.new(),
            record_code="REC-2026-0512-EV",
            record_type=ClinicalRecordType.CONSULTATION,
            location_name="Madrid",
            chief_complaint="x",
            signed_by_id=c.doctor_id,
        )
        c.sign(**kwargs)
        with pytest.raises(ConsultationAlreadySigned) as exc:
            c.sign(**kwargs)
        assert exc.value.code == "consultation.already_signed"

    def test_blocks_when_incomplete(self):
        c = make_consultation()
        c.autosave(note={"subjective": "x"})
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
        assert verify_chain([result.record]) == (SealStatus.OK,)
        assert result.record.seal == compute_seal(replace(result.record, seal=None), None)
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


class TestPartialVitals:
    def test_update_vitals_merges_and_reports_only_changed_fields(self):
        c = make_consultation()
        c.update_vitals({"blood_pressure": "120/80", "heart_rate": 70}, datetime(2026, 5, 12, 9, 5))
        changed = c.update_vitals({"weight": Decimal("70"), "heart_rate": 70})
        assert changed == ("weight",)
        assert c.vitals.blood_pressure == "120/80"
        assert c.vitals.heart_rate == 70

    def test_null_clears_a_field(self):
        c = make_consultation()
        c.update_vitals({"heart_rate": 70})
        assert c.update_vitals({"heart_rate": None}) == ("heart_rate",)
        assert c.vitals.is_empty()

    def test_no_change_leaves_last_saved_at_alone(self):
        c = make_consultation()
        c.update_vitals({"heart_rate": 70}, datetime(2026, 5, 12, 9, 5))
        assert c.update_vitals({"heart_rate": 70}, datetime(2026, 5, 12, 9, 30)) == ()
        assert c.last_saved_at == datetime(2026, 5, 12, 9, 5)

    def test_revalidates_and_rejects_unknown_fields(self):
        c = make_consultation()
        with pytest.raises(InvalidValueObject) as exc:
            c.update_vitals({"blood_pressure": "high"})
        assert exc.value.code == "vitals.invalid_blood_pressure"
        with pytest.raises(InvalidValueObject) as exc:
            c.update_vitals({"mood": 3})
        assert exc.value.code == "vitals.unknown_field"

    def test_refused_once_signed(self):
        c = make_consultation()
        c.status = ConsultationStatus.SIGNED
        with pytest.raises(ConsultationAlreadySigned):
            c.update_vitals({"heart_rate": 70})


class TestAutosaveChanges:
    def test_reports_only_the_sections_whose_text_changed(self):
        c = make_consultation()
        first = c.autosave(note={"subjective": "tos", "plan": "reposo"})
        assert set(first.note_keys) == {"subjective", "plan"}
        again = c.autosave(note={"subjective": "tos", "plan": "reposo y líquidos"})
        assert again.note_keys == ("plan",)
        assert c.autosave(note={"plan": "reposo y líquidos"}).note_keys == ()

    def test_vitals_in_an_autosave_do_not_erase_the_others(self):
        c = make_consultation()
        c.update_vitals({"blood_pressure": "130/85"})
        changes = c.autosave(vitals={"weight": Decimal("70")})
        assert changes.vitals == ("weight",)
        assert c.vitals.blood_pressure == "130/85"
