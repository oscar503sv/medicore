"""Consultation use cases — the bridge from an appointment to a signed medical record."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.audit import append_coalesced, audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import (
    ConsultationNotStarted,
    EntityNotFound,
    ValidationError,
)
from medicore.application.common.fees import ensure_can_price
from medicore.application.common.permissions import (
    Permission,
    ensure_not_support,
    ensure_permission,
    has_permission,
)
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.application.use_cases.note_templates import (
    available_templates,
    find_template,
    problems_prefill,
)
from medicore.domain.entities.application import ApplicationDraft
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.entities.procedure import ProcedureDraft
from medicore.domain.enums import AppointmentStatus, ClinicalRecordType, Role
from medicore.domain.services.note_templates import resolve_template
from medicore.domain.shared.errors import DomainError, PermissionDenied
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    InsurerId,
    LocationId,
    ProcedureTypeId,
    RecordId,
    UserId,
)
from medicore.domain.value_objects.clinical_note import ClinicalNote
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.note_settings import NoteSettings
from medicore.domain.value_objects.vitals import Vitals


@dataclass(frozen=True, slots=True)
class SignConsultationCommand:
    consultation_id: ConsultationId
    chief_complaint: str = ""
    vaccines: tuple[VaccineAdministration, ...] = ()


@dataclass(frozen=True, slots=True)
class ConsultationPatch:
    """An idempotent autosave patch for the live consultation."""

    vitals: Mapping[str, object] | None = None  # only the fields to change
    note: dict[str, str] | None = None  # section key -> text


@dataclass(frozen=True, slots=True)
class ConsultationVitalsView:
    """What nursing sees of a consultation: the patient, the booking and the vitals, never
    the note. The router serializes only these non-clinical fields."""

    consultation: Consultation
    patient: Patient | None
    appointment: Appointment | None
    doctor_name: str | None


@dataclass(frozen=True, slots=True)
class AppointmentVitalsView:
    """The vitals of an appointment: the consultation's once it exists, otherwise the ones
    nursing took while the patient waited. Never the note."""

    appointment_id: AppointmentId
    appointment: Appointment | None
    consultation: Consultation | None
    patient: Patient | None
    doctor_name: str | None
    vitals: Vitals
    last_saved_at: datetime | None

    @property
    def phase(self) -> str:
        return "consultation" if self.consultation is not None else "triage"

    @classmethod
    def of_consultation(cls, view: ConsultationVitalsView) -> AppointmentVitalsView:
        c = view.consultation
        return cls(
            c.appointment_id, view.appointment, c, view.patient, view.doctor_name,
            c.vitals, c.last_saved_at,
        )

    @classmethod
    def of_appointment(
        cls, appointment: Appointment, patient: Patient | None, doctor_name: str | None
    ) -> AppointmentVitalsView:
        return cls(
            appointment.id, appointment, None, patient, doctor_name,
            appointment.pre_vitals, appointment.pre_vitals_saved_at,
        )


def _ensure_author(actor: ActorContext, doctor_id: UserId, verb: str) -> None:
    """Clinical content belongs to the consultation's doctor; no grant reaches it."""
    ensure_not_support(actor)
    if actor.role != Role.DOCTOR or actor.user_id != doctor_id:
        raise PermissionDenied(
            f"only the consultation's doctor may {verb} it", code="consultation.not_own"
        )


def _may_start(actor: ActorContext, doctor_id: UserId) -> bool:
    return actor.role != Role.DOCTOR or actor.user_id == doctor_id


def _patient_subject(patient: Patient | None) -> str | None:
    return subject(patient.code, patient.full_name) if patient else None


class StartConsultation:
    """Open a consultation for an appointment and move the appointment to in_progress."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, appointment_id: AppointmentId) -> Consultation:
        ensure_permission(actor, Permission.CONSULTATIONS_START)
        ensure_not_support(actor)
        with self._uow:
            # Two starts queue here; the second finds the first's consultation instead of
            # inserting a duplicate.
            appointment = self._uow.appointments.get_for_update(appointment_id)
            if appointment is None:
                raise EntityNotFound("Appointment", appointment_id)
            if not _may_start(actor, appointment.doctor_id):
                raise PermissionDenied(
                    "doctors may only start their own consultations", code="consultation.not_own"
                )

            existing = self._uow.consultations.get_by_appointment(appointment_id)
            if existing is not None:
                return existing

            patient = self._uow.patients.get_by_id(appointment.patient_id)
            # Nursing's waiting-room readings move into the consultation (and out of the
            # appointment) in the same transaction that creates it.
            pre_vitals, pre_saved_at = appointment.take_pre_vitals()
            consultation = Consultation(
                id=ConsultationId.new(),
                tenant_id=actor.tenant_id,
                appointment_id=appointment_id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                started_at=self._clock.now(),
                vitals=pre_vitals,
                last_saved_at=None if pre_vitals.is_empty() else pre_saved_at,
                note=self._opening_note(actor, appointment, patient),
            )
            carried_keys = pre_vitals.filled_fields()
            carried = {"pre_vitals": list(carried_keys)} if carried_keys else {}
            appointment.start()
            self._uow.appointments.save(appointment)
            self._uow.consultations.save(consultation)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "consultation.started", "Consultation",
                    str(consultation.id),
                    subject=_patient_subject(patient), **carried,
                )
            )
            self._uow.commit()
        return consultation

    def _opening_note(self, actor: ActorContext, appointment: Appointment,
                      patient: Patient | None) -> ClinicalNote:
        """A blank note in the template the clinic's rules (or the doctor) pick."""
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        doctor = self._uow.users.get_by_id(appointment.doctor_id)
        templates = available_templates(self._uow)
        key = resolve_template(
            tenant.note_settings if tenant else NoteSettings(),
            appointment_type=appointment.type,
            first_visit=not self._uow.medical_records.list_by_patient(appointment.patient_id),
            favourite=doctor.preferences.note_template if doctor else None,
            available=templates,
        )
        return problems_prefill(ClinicalNote.blank(templates[key]), patient.tags if patient else [])


class GetConsultation:
    """Load a single consultation for the doctor who owns it. Opening it is audited, once
    per window: the screen polls to pick up nursing's vitals."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, consultation_id: ConsultationId) -> Consultation:
        ensure_permission(actor, Permission.CONSULTATIONS_EDIT)
        with self._uow:
            consultation = self._uow.consultations.get_by_id(consultation_id)
            if consultation is None:
                raise EntityNotFound("Consultation", consultation_id)
            _ensure_author(actor, consultation.doctor_id, "view")
            patient = self._uow.patients.get_by_id(consultation.patient_id)
            append_coalesced(
                self._uow,
                audit_entry(
                    actor, self._clock.now(), "consultation.viewed", "Consultation",
                    str(consultation.id), scope="full", subject=_patient_subject(patient),
                ),
                keys=("full",),
            )
            self._uow.commit()
        return consultation


class GetConsultationVitals:
    """The non-clinical view of a consultation, found from its appointment (the agenda does
    not carry the consultation id). For whoever records vitals."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, appointment_id: AppointmentId
    ) -> ConsultationVitalsView:
        _ensure_vitals_access(actor)
        with self._uow:
            consultation = self._uow.consultations.get_by_appointment(appointment_id)
            if consultation is None:
                raise ConsultationNotStarted(appointment_id)
            _ensure_vitals_author(actor, consultation)
            patient = self._uow.patients.get_by_id(consultation.patient_id)
            append_coalesced(
                self._uow,
                audit_entry(
                    actor, self._clock.now(), "consultation.viewed", "Consultation",
                    str(consultation.id), scope="vitals", subject=_patient_subject(patient),
                ),
                keys=("vitals",),
            )
            self._uow.commit()
            view = _vitals_view(self._uow, consultation, patient)
        return view


def _vitals_view(
    uow: UnitOfWork, consultation: Consultation, patient: Patient | None
) -> ConsultationVitalsView:
    doctor = uow.users.get_by_id(consultation.doctor_id)
    return ConsultationVitalsView(
        consultation,
        patient,
        uow.appointments.get_by_id(consultation.appointment_id),
        doctor.name if doctor else None,
    )


def _ensure_vitals_access(actor: ActorContext) -> None:
    """Checked before loading anything, so a refused actor learns nothing about the
    consultation."""
    ensure_not_support(actor)
    if not has_permission(actor, Permission.CONSULTATIONS_VITALS):
        ensure_permission(actor, Permission.CONSULTATIONS_EDIT)


def _ensure_vitals_author(actor: ActorContext, consultation: Consultation) -> None:
    # Whoever holds the vitals permission records them in any open consultation of the
    # clinic (there is no nurse-to-doctor assignment); otherwise only the doctor's own.
    if not has_permission(actor, Permission.CONSULTATIONS_VITALS):
        _ensure_author(actor, consultation.doctor_id, "edit")


def _ensure_pre_vitals_author(actor: ActorContext, appointment: Appointment) -> None:
    if not has_permission(actor, Permission.CONSULTATIONS_VITALS):
        _ensure_author(actor, appointment.doctor_id, "edit")


def _ensure_confirmed(appointment: Appointment) -> None:
    if appointment.status != AppointmentStatus.CONFIRMED:
        raise DomainError(
            "the appointment no longer takes vitals", code="appointment.vitals_closed"
        )


def _pre_vitals_view(
    uow: UnitOfWork, appointment: Appointment, patient: Patient | None
) -> AppointmentVitalsView:
    doctor = uow.users.get_by_id(appointment.doctor_id)
    return AppointmentVitalsView.of_appointment(
        appointment, patient, doctor.name if doctor else None
    )


@dataclass(frozen=True, slots=True)
class _Audit:
    action: str
    meta: Mapping[str, object]
    keys: tuple[str, ...] = ()
    coalesce: bool = False  # autosave-driven: skip repeats of the same keys in a window


class _ConsultationEditor:
    """Shared loading/permission/persistence for the draft-editing use cases."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _load(self, actor: ActorContext, consultation_id: ConsultationId) -> Consultation:
        ensure_permission(actor, Permission.CONSULTATIONS_EDIT)
        # Locked: an edit that read the draft before a sign committed would otherwise save
        # status=draft back over the signed consultation.
        consultation = self._uow.consultations.get_for_update(consultation_id)
        if consultation is None:
            raise EntityNotFound("Consultation", consultation_id)
        _ensure_author(actor, consultation.doctor_id, "edit")
        return consultation

    def _save(
        self,
        actor: ActorContext,
        consultation: Consultation,
        *audits: _Audit,
    ) -> None:
        """Persist and audit in one transaction. Audit metadata carries names (sections,
        fields, template keys), never clinical text."""
        with self._uow:
            self._uow.consultations.save(consultation)
            if audits:
                patient = self._uow.patients.get_by_id(consultation.patient_id)
                for item in audits:
                    entry = audit_entry(
                        actor, self._clock.now(), item.action, "Consultation",
                        str(consultation.id), subject=_patient_subject(patient), **item.meta,
                    )
                    if item.coalesce:
                        append_coalesced(self._uow, entry, item.keys)
                    else:
                        self._uow.audit.append(entry)
            self._uow.commit()

    def _save_draft(
        self, actor: ActorContext, consultation: Consultation, section: str, op: str
    ) -> None:
        self._save(
            actor, consultation,
            _Audit("consultation.draft_changed", {"section": section, "op": op}),
        )


class AutosaveConsultation(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, patch: ConsultationPatch
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        changes = consultation.autosave(
            vitals=patch.vitals, note=patch.note, when=self._clock.now()
        )
        audits = []
        if changes.note_keys:
            audits.append(
                _Audit("consultation.note_updated", {}, keys=changes.note_keys, coalesce=True)
            )
        if changes.vitals:
            audits.append(
                _Audit("consultation.vitals_updated", {}, keys=changes.vitals, coalesce=True)
            )
        self._save(actor, consultation, *audits)
        return consultation


class UpdateConsultationVitals(_ConsultationEditor):
    """Record vitals: nursing (``consultations.vitals``) in any open consultation, or the
    doctor in their own. Only the given fields change."""

    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId,
        changes: Mapping[str, object],
    ) -> ConsultationVitalsView:
        _ensure_vitals_access(actor)
        with self._uow:
            # Locked inside the unit of work so the lock lasts until the commit.
            consultation = self._uow.consultations.get_for_update(consultation_id)
            if consultation is None:
                raise EntityNotFound("Consultation", consultation_id)
            return self._write(actor, consultation, changes)

    def _write(
        self, actor: ActorContext, consultation: Consultation, changes: Mapping[str, object]
    ) -> ConsultationVitalsView:
        """Merge into an already locked consultation, audit and commit."""
        _ensure_vitals_author(actor, consultation)
        now = self._clock.now()
        changed = consultation.update_vitals(changes, now)
        patient = self._uow.patients.get_by_id(consultation.patient_id)
        if changed:
            self._uow.consultations.save(consultation)
            append_coalesced(
                self._uow,
                audit_entry(
                    actor, now, "consultation.vitals_updated", "Consultation",
                    str(consultation.id), subject=_patient_subject(patient),
                ),
                changed,
            )
            self._uow.commit()
        return _vitals_view(self._uow, consultation, patient)


class GetAppointmentVitals:
    """Vitals of an appointment for whoever records them: the consultation's when it has
    started, the waiting-room readings of a confirmed appointment before that."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, appointment_id: AppointmentId
    ) -> AppointmentVitalsView:
        _ensure_vitals_access(actor)
        with self._uow:
            consultation = self._uow.consultations.get_by_appointment(appointment_id)
            if consultation is not None:
                _ensure_vitals_author(actor, consultation)
                patient = self._uow.patients.get_by_id(consultation.patient_id)
                self._audit_view(actor, "Consultation", str(consultation.id), patient)
                self._uow.commit()
                return AppointmentVitalsView.of_consultation(
                    _vitals_view(self._uow, consultation, patient)
                )
            appointment = self._uow.appointments.get_by_id(appointment_id)
            if appointment is None:
                raise EntityNotFound("Appointment", appointment_id)
            _ensure_pre_vitals_author(actor, appointment)
            _ensure_confirmed(appointment)
            patient = self._uow.patients.get_by_id(appointment.patient_id)
            self._audit_view(actor, "Appointment", str(appointment.id), patient)
            self._uow.commit()
            return _pre_vitals_view(self._uow, appointment, patient)

    def _audit_view(
        self, actor: ActorContext, entity_type: str, entity_id: str, patient: Patient | None
    ) -> None:
        append_coalesced(
            self._uow,
            audit_entry(
                actor, self._clock.now(), "consultation.viewed", entity_type, entity_id,
                scope="vitals", subject=_patient_subject(patient),
            ),
            keys=("vitals",),
        )


class UpdateAppointmentVitals:
    """Record vitals from the appointment: into the consultation once it exists, otherwise
    into the confirmed appointment (nursing triage).

    Lock order: the consultation and the appointment are never held together. Start locks
    the appointment and then inserts the consultation; sign locks the consultation and then
    the appointment. Taking both here, in either order, could deadlock with one of them.
    """

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock
        self._consultation_writer = UpdateConsultationVitals(uow, clock)

    def execute(
        self, actor: ActorContext, appointment_id: AppointmentId, changes: Mapping[str, object]
    ) -> AppointmentVitalsView:
        _ensure_vitals_access(actor)
        consultation_id = self._consultation_id(appointment_id)
        if consultation_id is None:
            view = self._record_pre(actor, appointment_id, changes)
            if view is not None:
                return view
            # A consultation started while this waited for the appointment: its vitals are
            # the ones that count now, so write there (the appointment lock is released).
            consultation_id = self._consultation_id(appointment_id)
            if consultation_id is None:
                raise ConsultationNotStarted(appointment_id)
        return AppointmentVitalsView.of_consultation(
            self._consultation_writer.execute(actor, consultation_id, changes)
        )

    def _consultation_id(self, appointment_id: AppointmentId) -> ConsultationId | None:
        with self._uow:
            consultation = self._uow.consultations.get_by_appointment(appointment_id)
            return consultation.id if consultation is not None else None

    def _record_pre(
        self, actor: ActorContext, appointment_id: AppointmentId, changes: Mapping[str, object]
    ) -> AppointmentVitalsView | None:
        """Returns None, with nothing written and the lock released, when the consultation
        exists by the time the appointment is locked."""
        with self._uow:
            appointment = self._uow.appointments.get_for_update(appointment_id)
            if appointment is None:
                raise EntityNotFound("Appointment", appointment_id)
            if (
                appointment.status == AppointmentStatus.IN_PROGRESS
                or self._uow.consultations.get_by_appointment(appointment_id) is not None
            ):
                return None
            _ensure_pre_vitals_author(actor, appointment)
            now = self._clock.now()
            changed = appointment.record_pre_vitals(changes, now)
            patient = self._uow.patients.get_by_id(appointment.patient_id)
            if changed:
                self._uow.appointments.save(appointment)
                append_coalesced(
                    self._uow,
                    audit_entry(
                        actor, now, "consultation.vitals_updated", "Appointment",
                        str(appointment.id), subject=_patient_subject(patient),
                    ),
                    changed,
                )
                self._uow.commit()
            return _pre_vitals_view(self._uow, appointment, patient)


class ChangeNoteTemplate(_ConsultationEditor):
    """Rewrite the draft note in another template the clinic allows (text follows its
    role). Refused when the clinic made its format mandatory."""

    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, template_key: str
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        template = find_template(self._uow, template_key)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        settings = tenant.note_settings if tenant else NoteSettings()
        previous = consultation.note.template
        if template.key != previous:
            if settings.locked:
                raise PermissionDenied(
                    "the clinic made its note format mandatory", code="note.template_locked"
                )
            if not settings.allows(template.key):
                raise ValidationError(
                    "the clinic has not enabled this template", code="note.template_not_enabled"
                )
        consultation.change_template(template, when=self._clock.now())
        patient = self._uow.patients.get_by_id(consultation.patient_id)
        if patient is not None:
            consultation.note = problems_prefill(consultation.note, patient.tags)
        audits = (
            [_Audit("consultation.template_changed", {"from": previous, "to": template.key})]
            if template.key != previous else []
        )
        self._save(actor, consultation, *audits)
        return consultation


class AddDiagnosis(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, diagnosis: IcdCode
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.add_diagnosis(diagnosis)
        self._save_draft(actor, consultation, "diagnoses", "added")
        return consultation


class RemoveDiagnosis(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, code: str
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_diagnosis(code)
        self._save_draft(actor, consultation, "diagnoses", "removed")
        return consultation


class AddPrescriptionDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, draft: PrescriptionDraft
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.add_prescription_draft(draft)
        self._save_draft(actor, consultation, "prescriptions", "added")
        return consultation


class RemovePrescriptionDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, index: int
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_prescription_draft(index)
        self._save_draft(actor, consultation, "prescriptions", "removed")
        return consultation


class AddApplicationDraft(_ConsultationEditor):
    """Indicate an in-clinic application; it reaches the nursing team when signing."""

    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, draft: ApplicationDraft
    ) -> Consultation:
        # In-clinic applications are an optional module.
        ensure_permission(actor, Permission.APPLICATIONS_VIEW)
        consultation = self._load(actor, consultation_id)
        consultation.add_application_draft(draft)
        self._save_draft(actor, consultation, "applications", "added")
        return consultation


class RemoveApplicationDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, index: int
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_application_draft(index)
        self._save_draft(actor, consultation, "applications", "removed")
        return consultation


class AddProcedureDraft(_ConsultationEditor):
    """Indicate a procedure; it becomes a pending procedure when the consultation is signed.
    The type's rules (who performs it, consent, follow-up, price) are frozen with the
    indication. It may be marked as included in the consultation fee (charged nothing)."""

    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId,
        type_id: ProcedureTypeId, indication: str, included: bool = False,
    ) -> Consultation:
        # Procedures are an optional module.
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        consultation = self._load(actor, consultation_id)
        if included:  # charging nothing for it is a fee decision
            ensure_can_price(actor, consultation.doctor_id)
        kind = self._uow.procedures.get_type(type_id)
        if kind is None:
            raise EntityNotFound("ProcedureType", type_id)
        if not kind.active:
            raise ValidationError("the procedure type is archived", code="procedure.type_inactive")
        consultation.add_procedure_draft(ProcedureDraft.of(kind, indication, included))
        self._save_draft(actor, consultation, "procedures", "added")
        return consultation


class RemoveProcedureDraft(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, index: int
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_procedure_draft(index)
        self._save_draft(actor, consultation, "procedures", "removed")
        return consultation


class AddExam(_ConsultationEditor):
    """Order a lab, imaging or other exam; it is frozen into the record when signing."""

    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, exam: ExamRequest
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.add_exam(exam)
        self._save_draft(actor, consultation, "exams", "added")
        return consultation


class RemoveExam(_ConsultationEditor):
    def execute(
        self, actor: ActorContext, consultation_id: ConsultationId, index: int
    ) -> Consultation:
        consultation = self._load(actor, consultation_id)
        consultation.remove_exam(index)
        self._save_draft(actor, consultation, "exams", "removed")
        return consultation


class SignConsultation:
    """Atomically sign a consultation: emit an immutable MedicalRecord, issue prescriptions,
    and complete the appointment — all in one transaction, with an audit entry."""

    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: SignConsultationCommand) -> MedicalRecord:
        ensure_permission(actor, Permission.RECORDS_SIGN)
        with self._uow:
            # Lock before validating or drawing a code: a second sign of the same
            # consultation waits here and then finds it signed.
            consultation = self._uow.consultations.get_for_update(cmd.consultation_id)
            if consultation is None:
                raise EntityNotFound("Consultation", cmd.consultation_id)
            _ensure_author(actor, consultation.doctor_id, "sign")
            # The appointment is locked before the record-code counter (lock order:
            # document, appointment, counter), so a cancellation cannot slip in between and
            # a waiting sign never holds the counter.
            appointment = self._uow.appointments.get_for_update(consultation.appointment_id)
            if appointment is None:
                raise EntityNotFound("Appointment", consultation.appointment_id)
            patient = self._uow.patients.get_by_id(consultation.patient_id)

            now = self._clock.now()
            # A signed consultation is always a CONSULTATION clinical record — the type is
            # inferred, never chosen. Other clinical record types come from their own future
            # modules.
            record_type = ClinicalRecordType.CONSULTATION
            record_code = self._codes.next_record_code(record_type, now.date())
            location_name = self._location_name(appointment.location_id)

            result = consultation.sign(
                record_id=RecordId.new(),
                record_code=record_code,
                record_type=record_type,
                location_name=location_name,
                chief_complaint=cmd.chief_complaint or appointment.reason,
                signed_by_id=actor.user_id,
                insurer_name=self._insurer_name(appointment.insurance_id),
                vaccines=cmd.vaccines,
                signed_at=now,
                applications_start=clinic_now(self._uow, actor.tenant_id, self._clock).replace(
                    second=0, microsecond=0
                ),
            )
            appointment.complete()
            self._uow.consultations.save(consultation)
            self._uow.medical_records.save(result.record)
            for prescription in result.prescriptions:
                self._uow.prescriptions.save(prescription)
            for order in result.applications:
                self._uow.applications.save_order(order)
            for procedure in result.procedures:
                self._uow.procedures.save(procedure)
            self._uow.appointments.save(appointment)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "consultation.signed", "MedicalRecord", str(result.record.id),
                    appointment_id=str(appointment.id),
                    seal=result.record.seal.digest if result.record.seal else None,
                    prescriptions=len(result.prescriptions),
                    applications=len(result.applications),
                    procedures=len(result.procedures),
                    exams=len(result.record.exams),
                    subject=subject(
                        result.record.code, patient.full_name if patient else None
                    ),
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

    def _insurer_name(self, insurance_id: InsurerId | None) -> str | None:
        """Resolve the appointment's insurer name (frozen into the record). None = self-pay."""
        if insurance_id is None:
            return None
        insurer = self._uow.insurers.get_by_id(insurance_id)
        return insurer.name if insurer is not None else None
