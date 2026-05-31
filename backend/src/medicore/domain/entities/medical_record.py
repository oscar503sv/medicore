"""MedicalRecord aggregate — a signed, immutable clinical record.

Immutability rule: once a record is ``signed`` it cannot be mutated. A correction produces
an **amendment**: a new record with status ``amended`` that references the original via
``amends_record_id``. The original is never edited.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.prescription import PrescriptionSnapshot
from medicore.domain.enums import RecordStatus, RecordType
from medicore.domain.shared.errors import RecordAlreadySigned
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
    type: RecordType
    encounter_at: datetime
    location_name: str
    chief_complaint: str
    soap: SoapNote
    vitals: Vitals
    signed_at: datetime
    signed_by_id: UserId
    status: RecordStatus = RecordStatus.SIGNED
    appointment_id: AppointmentId | None = None
    consultation_id: ConsultationId | None = None
    diagnoses: tuple[IcdCode, ...] = ()
    prescriptions: tuple[PrescriptionSnapshot, ...] = ()
    vaccines: tuple[VaccineAdministration, ...] = ()
    attachments: tuple[AttachmentRef, ...] = ()
    amends_record_id: RecordId | None = None  # set on amendments

    def __post_init__(self) -> None:
        # Normalize any list inputs to tuples so the aggregate is truly immutable.
        for name in ("diagnoses", "prescriptions", "vaccines", "attachments"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))

    @property
    def is_amendment(self) -> bool:
        return self.amends_record_id is not None

    def amend(
        self,
        *,
        new_id: RecordId,
        author_id: UserId,
        signed_at: datetime | None = None,
        **changes: object,
    ) -> MedicalRecord:
        """Create an amended copy of this record. Does not mutate the original.

        Only signed records can be amended. The returned record has status ``amended`` and
        points back at this record via ``amends_record_id``.
        """
        if self.status not in (RecordStatus.SIGNED, RecordStatus.AMENDED):
            raise RecordAlreadySigned(
                "Only a signed (or previously amended) record can be amended"
            )
        return replace(
            self,
            id=new_id,
            status=RecordStatus.AMENDED,
            author_id=author_id,
            signed_by_id=author_id,
            signed_at=signed_at or datetime.now(UTC),
            amends_record_id=self.id,
            **changes,  # type: ignore[arg-type]
        )
