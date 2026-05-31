"""Prescription aggregate plus its draft (mutable) and snapshot (immutable) forms."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from medicore.domain.enums import PrescriptionStatus
from medicore.domain.shared.identifiers import (
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)


@dataclass(frozen=True, slots=True)
class PrescriptionDraft:
    """An in-progress prescription captured during a consultation (mutable container).

    Held inside the Consultation; turned into a Prescription + PrescriptionSnapshot on sign.
    """

    drug: str
    dose: str  # "20 mg"
    schedule: str  # "1× día · mañana"
    duration_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True, slots=True)
class PrescriptionSnapshot:
    """Immutable copy of a prescription, embedded into a signed MedicalRecord."""

    drug: str
    dose: str
    schedule: str
    start_date: date
    end_date: date | None = None
    duration_days: int | None = None


@dataclass(slots=True)
class Prescription:
    """A prescription issued to a patient (its own aggregate so it can be tracked/renewed)."""

    id: PrescriptionId
    tenant_id: TenantId
    patient_id: PatientId
    prescriber_id: UserId
    drug: str
    dose: str
    schedule: str
    start_date: date
    end_date: date | None = None  # None = indefinite
    duration_days: int | None = None
    status: PrescriptionStatus = PrescriptionStatus.ACTIVE
    record_id: RecordId | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def complete(self) -> None:
        self.status = PrescriptionStatus.COMPLETED

    def cancel(self) -> None:
        self.status = PrescriptionStatus.CANCELLED

    def snapshot(self) -> PrescriptionSnapshot:
        return PrescriptionSnapshot(
            drug=self.drug,
            dose=self.dose,
            schedule=self.schedule,
            start_date=self.start_date,
            end_date=self.end_date,
            duration_days=self.duration_days,
        )

    @staticmethod
    def from_draft(
        draft: PrescriptionDraft,
        *,
        id: PrescriptionId,
        tenant_id: TenantId,
        patient_id: PatientId,
        prescriber_id: UserId,
        record_id: RecordId | None = None,
        issued_on: date | None = None,
    ) -> Prescription:
        start = draft.start_date or issued_on or date.today()
        end = draft.end_date
        if end is None and draft.duration_days is not None:
            from datetime import timedelta

            end = start + timedelta(days=draft.duration_days)
        return Prescription(
            id=id,
            tenant_id=tenant_id,
            patient_id=patient_id,
            prescriber_id=prescriber_id,
            drug=draft.drug,
            dose=draft.dose,
            schedule=draft.schedule,
            start_date=start,
            end_date=end,
            duration_days=draft.duration_days,
            record_id=record_id,
        )
