"""MedicalRecord aggregate — a signed, immutable clinical record.

Immutability rule: once a record is ``signed`` it cannot be mutated. A correction produces
an **amendment**: a new record with status ``amended`` that references the original via
``amends_record_id``. The original is never edited.

Only the record's author amends it, always with a reason, and the versions form a single
line: a record is amended at most once, so the current version is the one nothing amends.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.prescription import PrescriptionSnapshot
from medicore.domain.enums import ClinicalRecordType, RecordStatus
from medicore.domain.shared.errors import InvalidValueObject, PermissionDenied, RecordAlreadySigned
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.clinical_note import ClinicalNote
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.vitals import Vitals

AMENDMENT_REASON_MIN = 10
AMENDMENT_REASON_MAX = 1000


@dataclass(frozen=True, slots=True)
class VaccineAdministration:
    """A vaccine dose recorded within a MedicalRecord."""

    name: str
    lot: str
    dose: str  # "2ª dosis"
    site: str  # "Deltoides izq."


@dataclass(frozen=True, slots=True)
class MedicalRecord:
    """A signed clinical record. Frozen at the dataclass level so fields cannot be reassigned.

    Lists are passed in at construction; callers must not mutate them afterwards (they are
    copied defensively into tuples on construction is not done here to keep it lightweight,
    but the aggregate exposes no mutators — use :meth:`amend` to create a new version).
    """

    id: RecordId
    tenant_id: TenantId
    code: str  # human-readable, e.g. "REC-2026-0512-CR"
    patient_id: PatientId
    author_id: UserId
    type: ClinicalRecordType
    encounter_at: datetime
    location_name: str
    chief_complaint: str
    note: ClinicalNote
    vitals: Vitals
    signed_at: datetime
    signed_by_id: UserId
    status: RecordStatus = RecordStatus.SIGNED
    insurer_name: str | None = None  # billed insurer frozen at sign time; None = self-pay
    appointment_id: AppointmentId | None = None
    consultation_id: ConsultationId | None = None
    diagnoses: tuple[IcdCode, ...] = ()
    prescriptions: tuple[PrescriptionSnapshot, ...] = ()
    vaccines: tuple[VaccineAdministration, ...] = ()
    exams: tuple[ExamRequest, ...] = ()  # exam orders issued in the consultation
    attachments: tuple[AttachmentRef, ...] = ()
    amends_record_id: RecordId | None = None  # set on amendments
    amendment_reason: str | None = None  # why it was amended; set on amendments

    def __post_init__(self) -> None:
        # Normalize any list inputs to tuples so the aggregate is truly immutable.
        for name in ("diagnoses", "prescriptions", "vaccines", "exams", "attachments"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))

    @property
    def is_amendment(self) -> bool:
        return self.amends_record_id is not None

    def amend(
        self,
        *,
        by: UserId,
        new_id: RecordId,
        signed_at: datetime,
        reason: str,
        chief_complaint: str | None = None,
        note: ClinicalNote | None = None,
    ) -> MedicalRecord:
        """Create an amended copy of this record. Does not mutate the original.

        Only the author amends, only signed (or amended) records can be amended, and the
        reason and at least one change are required. The returned record has status
        ``amended`` and points back at this record via ``amends_record_id``; ``author_id``
        stays the clinical author, ``signed_by_id`` and ``signed_at`` say who and when.
        """
        if self.status not in (RecordStatus.SIGNED, RecordStatus.AMENDED):
            raise RecordAlreadySigned(
                "Only a signed (or previously amended) record can be amended",
                code="record.not_amendable",
            )
        if by != self.author_id:
            raise PermissionDenied(
                "only the record's author may amend it", code="record.not_own"
            )
        reason = reason.strip()
        if not AMENDMENT_REASON_MIN <= len(reason) <= AMENDMENT_REASON_MAX:
            raise InvalidValueObject(
                "The amendment reason is too short or too long",
                code="record.amend_reason_invalid",
                min=AMENDMENT_REASON_MIN, max=AMENDMENT_REASON_MAX,
            )
        changes: dict[str, object] = {}
        if chief_complaint is not None and chief_complaint.strip() != self.chief_complaint.strip():
            changes["chief_complaint"] = chief_complaint
        if note is not None and _note_changed(self.note, note):
            changes["note"] = note
        if not changes:
            raise InvalidValueObject(
                "An amendment must change something", code="record.amend_empty"
            )
        return replace(
            self,
            id=new_id,
            status=RecordStatus.AMENDED,
            signed_by_id=by,
            signed_at=signed_at,
            amends_record_id=self.id,
            amendment_reason=reason,
            **changes,  # type: ignore[arg-type]
        )


def _note_changed(current: ClinicalNote, proposed: ClinicalNote) -> bool:
    return any(
        a.text.strip() != b.text.strip()
        for a, b in zip(current.sections, proposed.sections, strict=True)
    )
