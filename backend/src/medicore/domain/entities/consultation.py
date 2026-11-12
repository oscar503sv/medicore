"""Consultation aggregate — the live, mutable encounter log ("consulta en curso").

While the doctor attends, the Consultation holds the editable draft (vitals, the
clinical note, diagnoses, prescription drafts, attachments). Signing it produces an immutable
``MedicalRecord`` plus issued ``Prescription`` objects and marks the appointment completed.

The actual atomic persistence (record + prescriptions + appointment status, all-or-nothing)
is orchestrated by the application layer. :meth:`sign` is the pure domain operation that
*computes* those outputs and flips the consultation to ``signed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.entities.application import ApplicationDraft, ApplicationOrder
from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.prescription import Prescription, PrescriptionDraft
from medicore.domain.entities.procedure import Procedure, ProcedureDraft
from medicore.domain.enums import (
    ApplicationOrderSource,
    ClinicalRecordType,
    ConsultationStatus,
)
from medicore.domain.services.note_templates import SOAP
from medicore.domain.shared.errors import ConsultationNotSignable
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    AppointmentId,
    ConsultationId,
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.clinical_note import ClinicalNote, NoteTemplate
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.vitals import Vitals

# A note is considered sign-ready at or above this completeness; below it the application
# layer should warn. The hard floor for signing is here.
MIN_COMPLETION_TO_SIGN = 60


@dataclass(slots=True)
class SignResult:
    """The outputs produced by signing a consultation, for the app layer to persist atomically."""

    record: MedicalRecord
    prescriptions: list[Prescription]
    applications: list[ApplicationOrder] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)


@dataclass(slots=True)
class Consultation:
    """The mutable state of an in-progress consultation."""

    id: ConsultationId
    tenant_id: TenantId
    appointment_id: AppointmentId
    patient_id: PatientId
    doctor_id: UserId
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    vitals: Vitals = field(default_factory=Vitals)
    note: ClinicalNote = field(default_factory=lambda: ClinicalNote.blank(SOAP))
    diagnoses: list[IcdCode] = field(default_factory=list)
    draft_prescriptions: list[PrescriptionDraft] = field(default_factory=list)
    draft_applications: list[ApplicationDraft] = field(default_factory=list)
    draft_procedures: list[ProcedureDraft] = field(default_factory=list)
    draft_exams: list[ExamRequest] = field(default_factory=list)
    attachments: list[AttachmentRef] = field(default_factory=list)
    status: ConsultationStatus = ConsultationStatus.DRAFT
    last_saved_at: datetime | None = None

    # ── draft editing ──
    def autosave(
        self,
        *,
        vitals: Vitals | None = None,
        note: dict[str, str] | None = None,
        when: datetime | None = None,
    ) -> None:
        """Persist a draft patch (idempotent): vitals and the text of note sections by
        key. Only allowed while in draft."""
        self._assert_draft()
        if vitals is not None:
            self.vitals = vitals
        if note:
            self.note = self.note.with_texts(note)
        self.last_saved_at = when or datetime.now(UTC)

    def change_template(self, template: NoteTemplate, when: datetime | None = None) -> None:
        """Rewrite the note in another template, carrying the text over by role."""
        self._assert_draft()
        if template.key != self.note.template:
            self.note = self.note.switch_to(template)
            self.last_saved_at = when or datetime.now(UTC)

    def add_diagnosis(self, diagnosis: IcdCode) -> None:
        self._assert_draft()
        if diagnosis not in self.diagnoses:
            self.diagnoses.append(diagnosis)

    def remove_diagnosis(self, code: str) -> None:
        self._assert_draft()
        self.diagnoses = [d for d in self.diagnoses if d.code != code.upper()]

    def add_prescription_draft(self, draft: PrescriptionDraft) -> None:
        self._assert_draft()
        self.draft_prescriptions.append(draft)

    def remove_prescription_draft(self, index: int) -> None:
        self._assert_draft()
        del self.draft_prescriptions[index]

    def add_application_draft(self, draft: ApplicationDraft) -> None:
        self._assert_draft()
        self.draft_applications.append(draft)

    def remove_application_draft(self, index: int) -> None:
        self._assert_draft()
        del self.draft_applications[index]

    def add_procedure_draft(self, draft: ProcedureDraft) -> None:
        self._assert_draft()
        self.draft_procedures.append(draft)

    def remove_procedure_draft(self, index: int) -> None:
        self._assert_draft()
        del self.draft_procedures[index]

    def add_exam(self, exam: ExamRequest) -> None:
        self._assert_draft()
        self.draft_exams.append(exam)

    def remove_exam(self, index: int) -> None:
        self._assert_draft()
        del self.draft_exams[index]

    def attach_document(self, ref: AttachmentRef) -> None:
        self._assert_draft()
        self.attachments.append(ref)

    # ── completion ──
    def compute_completion(self) -> int:
        """Heuristic completeness percentage (0..100) used by the UI ring and sign guard.

        Weights: the note's required sections (60%), at least one diagnosis (20%), any
        vitals (20%).
        """
        note_score = self.note.completion_ratio() * 60
        dx_score = 20 if self.diagnoses else 0
        vitals_score = 20 if not self.vitals.is_empty() else 0
        return int(round(note_score + dx_score + vitals_score))

    def missing_for_sign(self) -> tuple[str, ...]:
        """What still counts against completion: blank required note sections (by key),
        then ``diagnosis`` and ``vitals``."""
        missing = list(self.note.missing_required())
        if not self.diagnoses:
            missing.append("diagnosis")
        if self.vitals.is_empty():
            missing.append("vitals")
        return tuple(missing)

    # ── signing ──
    def sign(
        self,
        *,
        record_id: RecordId,
        record_code: str,
        record_type: ClinicalRecordType,
        location_name: str,
        chief_complaint: str,
        signed_by_id: UserId,
        insurer_name: str | None = None,
        vaccines: tuple[VaccineAdministration, ...] = (),
        prescription_ids: list[PrescriptionId] | None = None,
        signed_at: datetime | None = None,
        applications_start: datetime | None = None,
    ) -> SignResult:
        """Validate minimum completeness, emit an immutable record + prescriptions, and
        mark this consultation as signed.

        ``prescription_ids`` must supply one id per draft prescription (so the app layer can
        use coordinated ids); if omitted, fresh UUIDs are generated.

        Indicated applications become internal orders for the nursing team, due from
        ``applications_start`` (the clinic wall-clock at signing); indicated procedures
        become pending procedures.
        """
        self._assert_draft()
        completion = self.compute_completion()
        if completion < MIN_COMPLETION_TO_SIGN:
            raise ConsultationNotSignable(
                f"Consultation only {completion}% complete; "
                f"minimum {MIN_COMPLETION_TO_SIGN}% required to sign",
                code="consultation.incomplete",
                completion=completion,
                min=MIN_COMPLETION_TO_SIGN,
            )

        now = signed_at or datetime.now(UTC)

        if prescription_ids is None:
            prescription_ids = [PrescriptionId.new() for _ in self.draft_prescriptions]
        if len(prescription_ids) != len(self.draft_prescriptions):
            raise ConsultationNotSignable(
                "prescription_ids count must match the number of draft prescriptions"
            )

        issued: list[Prescription] = [
            Prescription.from_draft(
                draft,
                id=pid,
                tenant_id=self.tenant_id,
                patient_id=self.patient_id,
                prescriber_id=signed_by_id,
                record_id=record_id,
                issued_on=now.date(),
            )
            for draft, pid in zip(self.draft_prescriptions, prescription_ids, strict=True)
        ]

        record = MedicalRecord(
            id=record_id,
            tenant_id=self.tenant_id,
            code=record_code,
            patient_id=self.patient_id,
            author_id=self.doctor_id,
            type=record_type,
            encounter_at=self.started_at,
            location_name=location_name,
            insurer_name=insurer_name,
            chief_complaint=chief_complaint,
            note=self.note,
            vitals=self.vitals,
            signed_at=now,
            signed_by_id=signed_by_id,
            appointment_id=self.appointment_id,
            consultation_id=self.id,
            diagnoses=tuple(self.diagnoses),
            prescriptions=tuple(p.snapshot() for p in issued),
            vaccines=vaccines,
            exams=tuple(self.draft_exams),
            attachments=tuple(self.attachments),
        )

        start = applications_start or now.replace(tzinfo=None)
        orders = [
            ApplicationOrder(
                id=ApplicationOrderId.new(),
                tenant_id=self.tenant_id,
                patient_id=self.patient_id,
                drug=d.drug,
                dose=d.dose,
                route=d.route,
                source=ApplicationOrderSource.INTERNAL,
                starts_at=start,
                created_by_id=signed_by_id,
                doses_total=d.doses_total,
                interval_hours=d.interval_hours,
                observation_minutes=d.observation_minutes,
                instructions=d.instructions,
                ordered_by_id=signed_by_id,
                consultation_id=self.id,
                created_at=now,
            )
            for d in self.draft_applications
        ]

        procedures = [
            Procedure.from_draft(
                d, tenant_id=self.tenant_id, patient_id=self.patient_id,
                ordered_by_id=signed_by_id, consultation_id=self.id, now=now,
            )
            for d in self.draft_procedures
        ]

        self.status = ConsultationStatus.SIGNED
        self.ended_at = now
        return SignResult(record=record, prescriptions=issued, applications=orders,
                          procedures=procedures)

    def _assert_draft(self) -> None:
        if self.status != ConsultationStatus.DRAFT:
            raise ConsultationNotSignable(
                "Consultation is already signed and cannot be modified",
                code="consultation.already_signed",
            )

