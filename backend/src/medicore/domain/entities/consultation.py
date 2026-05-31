"""Consultation aggregate — the live, mutable encounter log ("consulta en curso").

While the doctor attends, the Consultation holds the editable draft (vitals, SOAP,
diagnoses, prescription drafts, attachments). Signing it produces an immutable
``MedicalRecord`` plus issued ``Prescription`` objects and marks the appointment completed.

The actual atomic persistence (record + prescriptions + appointment status, all-or-nothing)
is orchestrated by the application layer. :meth:`sign` is the pure domain operation that
*computes* those outputs and flips the consultation to ``signed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.prescription import Prescription, PrescriptionDraft
from medicore.domain.enums import ConsultationStatus, RecordType
from medicore.domain.shared.errors import ConsultationNotSignable
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals

# A note is considered sign-ready at or above this completeness; below it the application
# layer should warn (the UI also warns under 80%). The hard floor for signing is here.
MIN_COMPLETION_TO_SIGN = 60


@dataclass(slots=True)
class SignResult:
    """The outputs produced by signing a consultation, for the app layer to persist atomically."""

    record: MedicalRecord
    prescriptions: list[Prescription]


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
    soap: SoapNote = field(default_factory=SoapNote)
    diagnoses: list[IcdCode] = field(default_factory=list)
    draft_prescriptions: list[PrescriptionDraft] = field(default_factory=list)
    attachments: list[AttachmentRef] = field(default_factory=list)
    status: ConsultationStatus = ConsultationStatus.DRAFT
    last_saved_at: datetime | None = None

    # ── draft editing ──
    def autosave(
        self,
        *,
        vitals: Vitals | None = None,
        soap: SoapNote | None = None,
        when: datetime | None = None,
    ) -> None:
        """Persist a draft patch (idempotent). Only allowed while in draft."""
        self._assert_draft()
        if vitals is not None:
            self.vitals = vitals
        if soap is not None:
            self.soap = soap
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

    def attach_document(self, ref: AttachmentRef) -> None:
        self._assert_draft()
        self.attachments.append(ref)

    # ── completion ──
    def compute_completion(self) -> int:
        """Heuristic completeness percentage (0..100) used by the UI ring and sign guard.

        Weights: SOAP sections (60%), at least one diagnosis (20%), any vitals (20%).
        """
        soap_score = (self.soap.filled_sections() / 4) * 60
        dx_score = 20 if self.diagnoses else 0
        vitals_score = 20 if not self.vitals.is_empty() else 0
        return int(round(soap_score + dx_score + vitals_score))

    # ── signing ──
    def sign(
        self,
        *,
        record_id: RecordId,
        record_code: str,
        record_type: RecordType,
        location_name: str,
        chief_complaint: str,
        signed_by_id: UserId,
        vaccines: tuple[VaccineAdministration, ...] = (),
        prescription_ids: list[PrescriptionId] | None = None,
        signed_at: datetime | None = None,
    ) -> SignResult:
        """Validate minimum completeness, emit an immutable record + prescriptions, and
        mark this consultation as signed.

        ``prescription_ids`` must supply one id per draft prescription (so the app layer can
        use coordinated ids); if omitted, fresh UUIDs are generated.
        """
        self._assert_draft()
        completion = self.compute_completion()
        if completion < MIN_COMPLETION_TO_SIGN:
            raise ConsultationNotSignable(
                f"Consultation only {completion}% complete; "
                f"minimum {MIN_COMPLETION_TO_SIGN}% required to sign"
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
            chief_complaint=chief_complaint,
            soap=self.soap,
            vitals=self.vitals,
            signed_at=now,
            signed_by_id=signed_by_id,
            appointment_id=self.appointment_id,
            consultation_id=self.id,
            diagnoses=tuple(self.diagnoses),
            prescriptions=tuple(p.snapshot() for p in issued),
            vaccines=vaccines,
            attachments=tuple(self.attachments),
        )

        self.status = ConsultationStatus.SIGNED
        self.ended_at = now
        return SignResult(record=record, prescriptions=issued)

    def _assert_draft(self) -> None:
        if self.status != ConsultationStatus.DRAFT:
            raise ConsultationNotSignable("Consultation is already signed and cannot be modified")
