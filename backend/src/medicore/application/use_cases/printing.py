"""Printable documents: everything a sheet needs, assembled in one read and audited.

The browser lays the sheet out and prints it; these use cases gather what goes on it (the
clinic and site, the signing doctor with their JVPM, the patient) and log that the document
was printed, since a reprinted prescription or certificate is clinical data leaving the
system. Each document follows the permissions of what it shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.procedure import Procedure
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.enums import NoteRole, PaperSize, Role
from medicore.domain.shared.identifiers import (
    AppointmentId,
    CertificateId,
    LocationId,
    PatientId,
    ProcedureId,
    RecordId,
    UserId,
)

RecordDocument = Literal["prescription", "exams", "record"]
ProcedureDocument = Literal["instructions", "consent", "pathology"]


@dataclass(frozen=True, slots=True)
class PrintClinic:
    name: str
    tax_id: str
    location_name: str
    address: str | None
    phone: str | None
    paper: PaperSize
    letterhead: bool


@dataclass(frozen=True, slots=True)
class PrintDoctor:
    name: str
    specialty: str | None
    jvpm: str | None
    sex: str | None = None  # for gendered wording ("la suscrita médica")


@dataclass(frozen=True, slots=True)
class PrintPatient:
    name: str
    code: str
    sex: str
    date_of_birth: date
    age: int  # completed years on the document's date
    allergies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrintContext:
    clinic: PrintClinic
    printed_at: datetime  # clinic wall-clock
    patient: PrintPatient | None = None
    doctor: PrintDoctor | None = None


@dataclass(frozen=True, slots=True)
class RecordPrint:
    context: PrintContext
    record: MedicalRecord
    indications: str | None  # the note's plan, when the doctor wrote one
    amends_code: str | None  # the original record's code, for an amendment


@dataclass(frozen=True, slots=True)
class CertificatePrint:
    context: PrintContext
    certificate: MedicalCertificate
    encounter_at: datetime
    ended_at: datetime


@dataclass(frozen=True, slots=True)
class ProcedurePrint:
    context: PrintContext
    procedure: Procedure


@dataclass(frozen=True, slots=True)
class AppointmentPrint:
    context: PrintContext
    appointment: Appointment


@dataclass(frozen=True, slots=True)
class AgendaRow:
    appointment: Appointment
    patient_name: str
    patient_code: str


@dataclass(frozen=True, slots=True)
class AgendaPrint:
    context: PrintContext
    day: date
    rows: tuple[AgendaRow, ...]


def _nothing() -> ValidationError:
    return ValidationError("this document has nothing to print", code="print.nothing_to_print")


class _Printer:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _tenant(self) -> Tenant:
        tenant = self._uow.tenants.get_by_id(self._uow.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", self._uow.tenant_id)
        return tenant

    def _context(
        self, *, location_id: LocationId | None = None, patient: Patient | None = None,
        doctor_id: UserId | None = None, on: date | None = None,
    ) -> PrintContext:
        tenant = self._tenant()
        location: Location = next(
            (loc for loc in tenant.locations if loc.id == location_id), tenant.primary_location
        )
        now = clinic_now(self._uow, tenant.id, self._clock)
        clinic = PrintClinic(
            name=tenant.legal_name, tax_id=tenant.tax_id, location_name=location.name,
            address=location.address, phone=location.phone,
            paper=tenant.print_settings.paper, letterhead=tenant.print_settings.letterhead,
        )
        return PrintContext(
            clinic=clinic, printed_at=now,
            patient=self._patient(patient, on or now.date()) if patient else None,
            doctor=self._doctor(doctor_id) if doctor_id else None,
        )

    @staticmethod
    def _patient(p: Patient, on: date) -> PrintPatient:
        return PrintPatient(
            name=p.full_name, code=p.code, sex=str(p.sex), date_of_birth=p.date_of_birth,
            age=p.age(on), allergies=tuple(p.allergies),
        )

    def _doctor(self, user_id: UserId) -> PrintDoctor | None:
        user = self._uow.users.get_by_id(user_id)
        if user is None:
            return None
        return PrintDoctor(name=user.name, specialty=user.specialty, jvpm=user.jvpm,
                           sex=str(user.sex) if user.sex else None)

    def _load_patient(self, patient_id: PatientId) -> Patient:
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)
        return patient

    def _location_of(self, appointment_id: AppointmentId | None) -> LocationId | None:
        if appointment_id is None:
            return None
        appointment = self._uow.appointments.get_by_id(appointment_id)
        return appointment.location_id if appointment else None

    def _audit(
        self, actor: ActorContext, document: str, entity_type: str, entity_id: str,
        code: str | None, patient: Patient | None,
    ) -> None:
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "document.printed", entity_type, entity_id,
                    document=document,
                    subject=subject(code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()


class PrintRecordDocument(_Printer):
    """The prescription, the exam order or the full copy of a signed record."""

    def execute(
        self, actor: ActorContext, record_id: RecordId, document: RecordDocument
    ) -> RecordPrint:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        record = self._uow.medical_records.get_by_id(record_id)
        if record is None:
            raise EntityNotFound("MedicalRecord", record_id)
        if (document == "prescription" and not record.prescriptions) or (
            document == "exams" and not record.exams
        ):
            raise _nothing()
        patient = self._load_patient(record.patient_id)
        amends_code = None
        if record.amends_record_id is not None:
            original = self._uow.medical_records.get_by_id(record.amends_record_id)
            amends_code = original.code if original else None
        context = self._context(
            location_id=self._location_of(record.appointment_id), patient=patient,
            doctor_id=record.signed_by_id, on=record.encounter_at.date(),
        )
        self._audit(actor, document, "MedicalRecord", str(record.id), record.code, patient)
        return RecordPrint(
            context=context, record=record, indications=record.note.text_for(NoteRole.PLAN) or None,
            amends_code=amends_code,
        )


class PrintCertificate(_Printer):
    def execute(self, actor: ActorContext, certificate_id: CertificateId) -> CertificatePrint:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        certificate = self._uow.certificates.get_by_id(certificate_id)
        if certificate is None:
            raise EntityNotFound("MedicalCertificate", certificate_id)
        if certificate.is_voided:
            raise ValidationError("a voided certificate is not printed",
                                  code="print.certificate_voided")
        record = self._uow.medical_records.get_by_id(certificate.record_id)
        if record is None:
            raise EntityNotFound("MedicalRecord", certificate.record_id)
        patient = self._load_patient(certificate.patient_id)
        context = self._context(
            location_id=self._location_of(record.appointment_id), patient=patient,
            doctor_id=certificate.doctor_id, on=record.encounter_at.date(),
        )
        self._audit(actor, "certificate", "MedicalCertificate", str(certificate.id),
                    certificate.code, patient)
        return CertificatePrint(context=context, certificate=certificate,
                                encounter_at=record.encounter_at, ended_at=record.signed_at)


class PrintProcedureDocument(_Printer):
    """Care instructions for the patient, the consent form to sign on paper, or the request
    that goes with the specimen to pathology."""

    def execute(
        self, actor: ActorContext, procedure_id: ProcedureId, document: ProcedureDocument
    ) -> ProcedurePrint:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        procedure = self._uow.procedures.get(procedure_id)
        if procedure is None:
            raise EntityNotFound("Procedure", procedure_id)
        has_content = {
            "instructions": bool((procedure.instructions or "").strip()),
            "consent": procedure.requires_consent,
            "pathology": procedure.takes_specimen or procedure.specimen_sent,
        }[document]
        if not has_content:
            raise _nothing()
        patient = self._load_patient(procedure.patient_id)
        doctor_id = (
            procedure.performed_by_id if document == "instructions" and procedure.performed_by_id
            else procedure.ordered_by_id
        )
        context = self._context(
            location_id=self._location_of(procedure.appointment_id), patient=patient,
            doctor_id=doctor_id,
        )
        self._audit(actor, document, "Procedure", str(procedure.id), procedure.type_name,
                    patient)
        return ProcedurePrint(context=context, procedure=procedure)


class PrintVaccinationCard(_Printer):
    """The card's doses come from the vaccination module; this adds the sheet's header."""

    def execute(self, actor: ActorContext, patient_id: PatientId) -> PrintContext:
        ensure_permission(actor, Permission.VACCINATIONS_VIEW)
        patient = self._load_patient(patient_id)
        context = self._context(patient=patient)
        self._audit(actor, "vaccination_card", "Patient", str(patient.id), patient.code,
                    patient)
        return context


class PrintAppointmentSlip(_Printer):
    """What the patient takes home: when, with whom and where (never the price)."""

    def execute(self, actor: ActorContext, appointment_id: AppointmentId) -> AppointmentPrint:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        appointment = self._uow.appointments.get_by_id(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        if actor.role == Role.DOCTOR and appointment.doctor_id != actor.user_id:
            raise EntityNotFound("Appointment", appointment_id)
        patient = self._load_patient(appointment.patient_id)
        context = self._context(
            location_id=appointment.location_id, patient=patient,
            doctor_id=appointment.doctor_id, on=appointment.scheduled_start.date(),
        )
        self._audit(actor, "appointment_slip", "Appointment", str(appointment.id),
                    appointment.code, patient)
        return AppointmentPrint(context=context, appointment=appointment)


class PrintAgenda(_Printer):
    """A doctor's appointments for one day (doctors only ever print their own)."""

    def execute(self, actor: ActorContext, day: date, doctor_id: UserId | None) -> AgendaPrint:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        if actor.role == Role.DOCTOR:
            doctor_id = actor.user_id
        if doctor_id is None:
            raise ValidationError("choose the doctor whose agenda to print",
                                  code="print.doctor_required")
        if self._uow.users.get_by_id(doctor_id) is None:
            raise EntityNotFound("User", doctor_id)
        appointments = sorted(self._uow.appointments.list_by_day(day, doctor_id),
                              key=lambda a: a.scheduled_start)
        rows = []
        for a in appointments:
            patient = self._uow.patients.get_by_id(a.patient_id)
            rows.append(AgendaRow(appointment=a, patient_name=patient.full_name if patient else "—",
                                  patient_code=patient.code if patient else ""))
        context = self._context(
            doctor_id=doctor_id,
            location_id=appointments[0].location_id if appointments else None,
        )
        self._audit(actor, "agenda", "Agenda", f"{doctor_id}:{day.isoformat()}",
                    day.isoformat(), None)
        return AgendaPrint(context=context, day=day, rows=tuple(rows))
