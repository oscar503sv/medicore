"""Printable documents and medical certificates: what each sheet carries, who may print or
issue it, and that every print is audited."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.auth import UpdateMyProfile
from medicore.application.use_cases.certificates import (
    IssueCertificateCommand,
    IssueMedicalCertificate,
    ListMedicalCertificates,
    VoidMedicalCertificate,
)
from medicore.application.use_cases.organization import UpdateLocation, UpdatePrintSettings
from medicore.application.use_cases.printing import (
    PrintAgenda,
    PrintAppointmentSlip,
    PrintCertificate,
    PrintProcedureDocument,
    PrintRecordDocument,
    PrintVaccinationCard,
)
from medicore.application.use_cases.users import UpdateUser
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.prescription import PrescriptionSnapshot
from medicore.domain.enums import (
    CertificateKind,
    ClinicalRecordType,
    ExamKind,
    PaperSize,
    Role,
    Sex,
)
from medicore.domain.shared.errors import InvalidValueObject, PermissionDenied
from medicore.domain.shared.identifiers import RecordId
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.print_settings import PrintSettings
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals
from tests.application.test_consultations import booked
from tests.application.test_procedures import _create
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

NOW = datetime(2026, 5, 20, 12, 0)


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _record(seed, *, plan="Reposo relativo, abundantes líquidos.", prescriptions=True,
            exams=()):
    record = MedicalRecord(
        id=RecordId.new(), tenant_id=seed.tenant.id, code="REC-2026-0520-CO-1",
        patient_id=seed.patient.id, author_id=seed.doctor.id,
        type=ClinicalRecordType.CONSULTATION, encounter_at=datetime(2026, 5, 20, 9),
        location_name="Sede", chief_complaint="Fiebre", soap=SoapNote("s", "o", "a", plan),
        vitals=Vitals(), signed_at=datetime(2026, 5, 20, 9, 30), signed_by_id=seed.doctor.id,
        diagnoses=(IcdCode("J06.9", "Infección aguda de vías respiratorias"),),
        prescriptions=(PrescriptionSnapshot("Paracetamol", "500 mg", "c/8 h",
                                            date(2026, 5, 20), duration_days=3),)
        if prescriptions else (),
        exams=tuple(exams),
    )
    seed.factory.store.medical_records[record.id.value] = record
    return record


def _actions(seed):
    return [e.action for e in _uow(seed).audit.list().items]


@pytest.fixture
def seed():
    s = seed_clinic()
    s.doctor.jvpm = "12345"
    s.doctor.specialty = "Ginecología"
    s.doctor.sex = Sex.FEMALE  # certificates and consents read "la suscrita médica"
    return s


class TestRecordDocuments:
    def test_prescription_carries_doctor_patient_clinic_and_indications(self, seed):
        record = _record(seed)
        doc = PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
            seed.doctor_actor, record.id, "prescription")
        ctx = doc.context
        assert (ctx.doctor.name, ctx.doctor.jvpm, ctx.doctor.specialty, ctx.doctor.sex) == (
            "Dra. Elena Ruiz", "12345", "Ginecología", "female")
        assert ctx.patient.code == seed.patient.code
        assert ctx.clinic.paper == PaperSize.HALF_LETTER and not ctx.clinic.letterhead
        assert doc.indications == "Reposo relativo, abundantes líquidos."
        assert "document.printed" in _actions(seed)

    def test_no_indications_when_the_plan_is_blank(self, seed):
        doc = PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
            seed.doctor_actor, _record(seed, plan="   ").id, "prescription")
        assert doc.indications is None

    @pytest.mark.parametrize("document", ["prescription", "exams"])
    def test_nothing_to_print(self, seed, document):
        record = _record(seed, prescriptions=False)
        with pytest.raises(ValidationError) as e:
            PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
                seed.doctor_actor, record.id, document)
        assert e.value.code == "print.nothing_to_print"
        assert "document.printed" not in _actions(seed)

    def test_exam_order(self, seed):
        record = _record(seed, exams=[ExamRequest("Ultrasonografía pélvica", ExamKind.IMAGING)])
        doc = PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
            seed.doctor_actor, record.id, "exams")
        assert doc.record.exams[0].kind == ExamKind.IMAGING

    def test_receptionist_without_records_view_is_refused(self, seed):
        reception = replace(seed.receptionist_actor, permissions=frozenset())
        with pytest.raises(PermissionDenied):
            PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
                reception, _record(seed).id, "prescription")

    def test_print_settings_and_site_phone_reach_the_header(self, seed):
        admin = seed.actor(seed.admin)
        UpdatePrintSettings(_uow(seed), FixedClock()).execute(
            admin, PrintSettings(PaperSize.LETTER, letterhead=True))
        UpdateLocation(_uow(seed), FixedClock()).execute(
            admin, seed.tenant.primary_location.id, phone=" 2222-3333 ")
        ctx = PrintRecordDocument(_uow(seed), FixedClock(NOW)).execute(
            seed.doctor_actor, _record(seed).id, "record").context
        assert (ctx.clinic.paper, ctx.clinic.letterhead, ctx.clinic.phone) == (
            PaperSize.LETTER, True, "2222-3333")
        assert "organization.print_settings_updated" in _actions(seed)


class TestCertificates:
    def _issue(self, seed, record, actor=None, **kw):
        cmd = IssueCertificateCommand(record_id=record.id, **{
            "kind": CertificateKind.REST, "rest_from": date(2026, 5, 20), "rest_days": 3, **kw})
        return IssueMedicalCertificate(_uow(seed), SequentialCodeGenerator(),
                                       FixedClock(NOW)).execute(actor or seed.doctor_actor, cmd)

    def test_issue_print_and_list(self, seed):
        record = _record(seed)
        c = self._issue(seed, record, include_diagnosis=True)
        assert c.code == "CM-2026-0001"
        assert c.diagnosis == "J06.9 Infección aguda de vías respiratorias"
        doc = PrintCertificate(_uow(seed), FixedClock(NOW)).execute(seed.doctor_actor, c.id)
        assert doc.certificate.rest_until == date(2026, 5, 22)
        assert doc.context.doctor.jvpm == "12345"
        listed = ListMedicalCertificates(_uow(seed)).execute(
            seed.actor(seed.nurse), patient_id=seed.patient.id)
        assert [x.id for x in listed] == [c.id]
        assert {"certificate.issued", "document.printed"} <= set(_actions(seed))

    def test_diagnosis_stays_private_by_default(self, seed):
        assert self._issue(seed, _record(seed)).diagnosis is None

    def test_only_the_signing_doctor_issues_and_voids(self, seed):
        other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="o@x.test")
        seed.factory.store.users[other.id.value] = other
        record = _record(seed)
        with pytest.raises(PermissionDenied) as e:
            self._issue(seed, record, actor=seed.actor(other))
        assert e.value.code == "certificate.not_own"
        c = self._issue(seed, record)
        with pytest.raises(PermissionDenied):
            VoidMedicalCertificate(_uow(seed), FixedClock()).execute(
                seed.actor(other), c.id, "error")

    def test_a_voided_certificate_is_not_printed(self, seed):
        c = self._issue(seed, _record(seed))
        VoidMedicalCertificate(_uow(seed), FixedClock()).execute(
            seed.doctor_actor, c.id, "Fecha equivocada")
        with pytest.raises(ValidationError) as e:
            PrintCertificate(_uow(seed), FixedClock(NOW)).execute(seed.doctor_actor, c.id)
        assert e.value.code == "print.certificate_voided"
        assert "certificate.voided" in _actions(seed)


class TestOtherDocuments:
    def test_procedure_documents_follow_what_the_procedure_has(self, seed):
        biopsy = _create(seed, seed.doctor_actor, "Biopsia de piel", indication="Lesión")
        printer = PrintProcedureDocument(_uow(seed), FixedClock(NOW))
        assert printer.execute(seed.doctor_actor, biopsy.id, "consent").procedure.id == biopsy.id
        assert printer.execute(seed.doctor_actor, biopsy.id, "pathology")
        with pytest.raises(ValidationError):  # nothing performed yet: no instructions
            printer.execute(seed.doctor_actor, biopsy.id, "instructions")
        suture = _create(seed, seed.doctor_actor)
        with pytest.raises(ValidationError):
            printer.execute(seed.doctor_actor, suture.id, "pathology")

    def test_vaccination_card_header(self, seed):
        ctx = PrintVaccinationCard(_uow(seed), FixedClock(NOW)).execute(
            seed.actor(seed.nurse), seed.patient.id)
        assert ctx.patient.name == seed.patient.full_name and ctx.doctor is None

    def test_appointment_slip_and_agenda(self, seed):
        appt = booked(seed, _uow(seed))
        slip = PrintAppointmentSlip(_uow(seed), FixedClock(NOW)).execute(
            seed.receptionist_actor, appt.id)
        assert slip.context.doctor.name == "Dra. Elena Ruiz"
        day = appt.scheduled_start.date()
        with pytest.raises(ValidationError) as e:
            PrintAgenda(_uow(seed), FixedClock(NOW)).execute(seed.receptionist_actor, day, None)
        assert e.value.code == "print.doctor_required"
        agenda = PrintAgenda(_uow(seed), FixedClock(NOW)).execute(seed.doctor_actor, day, None)
        assert [r.appointment.id for r in agenda.rows] == [appt.id]


class TestJvpm:
    def test_admin_and_the_doctor_set_it(self, seed):
        user = UpdateUser(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), seed.doctor.id, jvpm=" 9876 ")
        assert user.jvpm == "9876"
        with pytest.raises(InvalidValueObject):
            UpdateUser(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), seed.doctor.id, jvpm="ABC")
        profile = UpdateMyProfile(seed.factory, FixedClock()).execute(
            seed.doctor_actor, jvpm="5555")
        assert profile.jvpm == "5555"

    def test_ignored_for_non_doctors(self, seed):
        profile = UpdateMyProfile(seed.factory, FixedClock()).execute(
            seed.actor(seed.nurse), jvpm="5555")
        assert profile.jvpm is None
