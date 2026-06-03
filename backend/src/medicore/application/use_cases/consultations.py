"""Consultation use cases — the bridge from an appointment to a signed medical record."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import (
    ensure_can_edit_consultation,
    ensure_can_sign_records,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import ClinicalRecordType, Role
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    LocationId,
    RecordId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals


@dataclass(frozen=True, slots=True)
class SignConsultationCommand:
    consultation_id: ConsultationId
    chief_complaint: str = ""
    vaccines: tuple[VaccineAdministration, ...] = ()


@dataclass(frozen=True, slots=True)
class ConsultationPatch:
    """An idempotent autosave patch for the live consultation."""

    vitals: Vitals | None = None
    soap: SoapNote | None = None


def _owns(actor: ActorContext, doctor_id: object) -> bool:
    return actor.role != Role.DOCTOR or actor.user_id == doctor_id


class StartConsultation:
    """Open a consultation for an appointment and move the appointment to in_progress."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, appointment_id: AppointmentId) -> Consultation:
        ensure_can_edit_consultation(actor)
        appointment = self._uow.appointments.get_by_id(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        if not _owns(actor, appointment.doctor_id):
            raise PermissionDenied("doctors may only start their own consultations")

        existing = self._uow.consultations.get_by_appointment(appointment_id)
        if existing is not None:
            return existing

        consultation = Consultation(
            id=ConsultationId.new(),
            tenant_id=actor.tenant_id,
            appointment_id=appointment_id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            started_at=self._clock.now(),
        )
        with self._uow:
            appointment.start()
            self._uow.appointments.save(appointment)
            self._uow.consultations.save(consultation)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "consultation.started", "Consultation",
                    str(consultation.id),
                )
            )
            self._uow.commit()
        return consultation


class GetConsultation:
    """Load a single consultation for viewing in the live consultation screen."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, consultation_id: ConsultationId) -> Consultation:
        ensure_can_edit_consultation(actor)
        consultation = self._uow.consultations.get_by_id(consultation_id)
        if consultation is None:
            raise EntityNotFound("Consultation", consultation_id)
        if not _owns(actor, consultation.doctor_id):
            raise PermissionDenied("doctors may only view their own consultations")
        return consultation


class _ConsultationEditor:
    """Shared loading/permission/persistence for the draft-editing use cases."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _load(self, actor: ActorContext, consultation_id: ConsultationId) -> Consultation:
        ensure_can_edit_consultation(actor)
        consultation = self._uow.consultations.get_by_id(consultation_id)
        if consultation is None:
            raise EntityNotFound("Consultation", consultation_id)
        if not _owns(actor, consultation.doctor_id):
            raise PermissionDenied("doctors may only edit their own consultations")
        return consultation

    def _save(self, consultation: Consultation) -> None:
        with self._uow:
            self._uow.consultations.save(consultation)
            self._uow.commit()


class AutosaveConsultation(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, patch: ConsultationPatch
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.autosave(vitals=patch.vitals, soap=patch.soap, when=self._clock.now())
        self._save(consultation)
        return consultation


class AddDiagnosis(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, diagnosis: IcdCode
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.add_diagnosis(diagnosis)
        self._save(consultation)
        return consultation


class RemoveDiagnosis(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, code: str
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_diagnosis(code)
        self._save(consultation)
        return consultation


class AddPrescriptionDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, draft: PrescriptionDraft
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.add_prescription_draft(draft)
        self._save(consultation)
        return consultation


class RemovePrescriptionDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, index: int
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_prescription_draft(index)
        self._save(consultation)
        return consultation


class AttachDocument(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, ref: AttachmentRef
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.attach_document(ref)
        self._save(consultation)
        return consultation


class SignConsultation:
    """Atomically sign a consultation: emit an immutable MedicalRecord, issue prescriptions,
    and complete the appointment — all in one transaction, with an audit entry."""

    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: SignConsultationCommand) -> MedicalRecord:
        ensure_can_sign_records(actor)
        consultation = self._uow.consultations.get_by_id(cmd.consultation_id)
        if consultation is None:
            raise EntityNotFound("Consultation", cmd.consultation_id)
        if not _owns(actor, consultation.doctor_id):
            raise PermissionDenied("doctors may only sign their own consultations")
        appointment = self._uow.appointments.get_by_id(consultation.appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", consultation.appointment_id)

        now = self._clock.now()
        # A signed consultation is always a CONSULTATION clinical record — the type is inferred,
        # never chosen. Other clinical record types come from their own future modules.
        record_type = ClinicalRecordType.CONSULTATION
        record_code = self._codes.next_record_code(record_type, now.date())
        location_name = self._location_name(appointment.location_id)

        with self._uow:
            result = consultation.sign(
                record_id=RecordId.new(),
                record_code=record_code,
                record_type=record_type,
                location_name=location_name,
                chief_complaint=cmd.chief_complaint or appointment.reason,
                signed_by_id=actor.user_id,
                vaccines=cmd.vaccines,
                signed_at=now,
            )
            appointment.complete()
            self._uow.consultations.save(consultation)
            self._uow.medical_records.save(result.record)
            for prescription in result.prescriptions:
                self._uow.prescriptions.save(prescription)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "consultation.signed", "MedicalRecord", str(result.record.id),
                    appointment_id=str(appointment.id),
                    prescriptions=len(result.prescriptions),
                )
            )
            self._uow.commit()
        return result.record

    def _location_name(self, location_id: LocationId) -> str:
        tenant = self._uow.tenants.get_by_id(self._uow.tenant_id)
        if tenant is not None:
            for location in tenant.locations:
                if location.id == location_id:
                    return location.name
        return "—"
