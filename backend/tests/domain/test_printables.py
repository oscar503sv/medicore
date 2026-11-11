"""Printable content rules: medical certificates, exam orders and the doctor's JVPM."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_certificate import MAX_REST_DAYS, MedicalCertificate
from medicore.domain.entities.user import normalize_jvpm
from medicore.domain.enums import CertificateKind, ClinicalRecordType, ExamKind
from medicore.domain.shared.errors import InvalidStateTransition, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AppointmentId,
    CertificateId,
    ConsultationId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote

NOW = datetime(2026, 5, 20, 10, 0)


def certificate(kind=CertificateKind.REST, **kw) -> MedicalCertificate:
    defaults = {"rest_from": date(2026, 5, 20), "rest_days": 3} if kind == CertificateKind.REST \
        else {}
    return MedicalCertificate(
        id=CertificateId.new(), tenant_id=TenantId.new(), code="CM-2026-0001",
        patient_id=PatientId.new(), record_id=RecordId.new(), doctor_id=UserId.new(),
        kind=kind, issued_at=NOW, **{**defaults, **kw},
    )


class TestCertificate:
    def test_rest_days_count_the_first_day(self):
        assert certificate().rest_until == date(2026, 5, 22)

    @pytest.mark.parametrize("kw,code", [
        ({"rest_from": None}, "certificate.rest_required"),
        ({"rest_days": 0}, "certificate.rest_days_range"),
        ({"rest_days": MAX_REST_DAYS + 1}, "certificate.rest_days_range"),
        ({"remarks": "x" * 1001}, "certificate.text_too_long"),
    ])
    def test_invalid(self, kw, code):
        with pytest.raises(InvalidValueObject) as e:
            certificate(**kw)
        assert e.value.code == code

    def test_attendance_drops_rest_fields_and_blank_text(self):
        c = certificate(CertificateKind.ATTENDANCE, rest_days=5, remarks="  ", addressee="")
        assert (c.rest_from, c.rest_days, c.rest_until, c.remarks, c.addressee) == (
            None, None, None, None, None)

    def test_void_needs_a_reason_and_happens_once(self):
        c = certificate()
        with pytest.raises(InvalidValueObject) as e:
            c.void(UserId.new(), " ", NOW)
        assert e.value.code == "certificate.void_reason_required"
        c.void(UserId.new(), "Fecha equivocada", NOW)
        assert c.is_voided and c.void_reason == "Fecha equivocada"
        with pytest.raises(InvalidStateTransition):
            c.void(UserId.new(), "otra vez", NOW)


class TestExamRequest:
    def test_trims_and_defaults_to_lab(self):
        e = ExamRequest("  Hemograma completo ", notes="  ")
        assert (e.name, e.kind, e.notes) == ("Hemograma completo", ExamKind.LAB, None)

    @pytest.mark.parametrize("kw,code", [
        ({"name": " "}, "exam.invalid_name"),
        ({"name": "x" * 201}, "exam.invalid_name"),
        ({"name": "Glucosa", "notes": "x" * 501}, "exam.notes_too_long"),
    ])
    def test_invalid(self, kw, code):
        with pytest.raises(InvalidValueObject) as e:
            ExamRequest(**kw)
        assert e.value.code == code

    def test_signing_freezes_the_exams_into_the_record(self):
        c = Consultation(id=ConsultationId.new(), tenant_id=TenantId.new(),
                         appointment_id=AppointmentId.new(), patient_id=PatientId.new(),
                         doctor_id=UserId.new(), soap=SoapNote("s", "o", "a", "p"),
                         diagnoses=[IcdCode("J06.9", "IRA")])
        c.add_exam(ExamRequest("Hemograma completo"))
        c.add_exam(ExamRequest("Ultrasonografía pélvica", ExamKind.IMAGING))
        c.remove_exam(0)
        result = c.sign(record_id=RecordId.new(), record_code="REC-1",
                        record_type=ClinicalRecordType.CONSULTATION, location_name="Sede",
                        chief_complaint="Dolor", signed_by_id=c.doctor_id, signed_at=NOW)
        assert [e.name for e in result.record.exams] == ["Ultrasonografía pélvica"]


class TestJvpm:
    @pytest.mark.parametrize("raw,expected", [(" 12345 ", "12345"), ("", None), (None, None)])
    def test_normalizes(self, raw, expected):
        assert normalize_jvpm(raw) == expected

    @pytest.mark.parametrize("raw", ["12-345", "JVPM 1", "12345678901"])
    def test_rejects_non_digits_or_too_long(self, raw):
        with pytest.raises(InvalidValueObject) as e:
            normalize_jvpm(raw)
        assert e.value.code == "user.invalid_jvpm"
