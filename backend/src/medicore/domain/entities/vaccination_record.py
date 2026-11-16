"""VaccinationRecord — one dose given, refused or contraindicated for a patient.

Clinical record semantics: never edited. A wrong entry is *voided* (with who, when and why)
and stays in the history; the corrected dose is recorded anew.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from medicore.domain.enums import (
    InjectionSite,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
    VaccineSupply,
)
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AppointmentId,
    PatientId,
    TenantId,
    UserId,
    VaccinationRecordId,
)
from medicore.domain.value_objects.fee import check_fee
from medicore.domain.value_objects.money import Money


class VaccinationAlreadyVoided(DomainError):
    code = "vaccination.already_voided"


@dataclass(slots=True)
class VaccinationRecord:
    id: VaccinationRecordId
    tenant_id: TenantId
    patient_id: PatientId
    vaccine_code: str
    dose_key: str | None  # scheduled dose it fulfils; None for doses outside the scheme
    outcome: VaccinationOutcome
    occurred_on: date
    source: VaccinationSource
    recorded_by_id: UserId
    # The vaccination appointment the dose was given in; None for doses recorded on their own.
    appointment_id: AppointmentId | None = None
    lot: str | None = None
    route: VaccineRoute | None = None
    site: InjectionSite | None = None
    notes: str | None = None
    # Who supplied a dose given here (None for anything else and for doses recorded before the
    # field existed), and the price copied when it was given in an appointment.
    supply: VaccineSupply | None = None
    listed_fee: Money | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    voided_at: datetime | None = None
    voided_by_id: UserId | None = None
    void_reason: str | None = None

    def __post_init__(self) -> None:
        self.lot = (self.lot or "").strip() or None
        self.notes = (self.notes or "").strip() or None
        # Traceability: a dose given here must say which lot went into the patient.
        if (
            self.outcome == VaccinationOutcome.ADMINISTERED
            and self.source == VaccinationSource.CLINIC
            and not self.lot
        ):
            raise InvalidValueObject(
                "a dose administered at the clinic requires its lot number",
                code="vaccination.lot_required",
            )
        self._check_supply()

    def _check_supply(self) -> None:
        given_here = (
            self.outcome == VaccinationOutcome.ADMINISTERED
            and self.source == VaccinationSource.CLINIC
        )
        if given_here and self.supply is None:
            raise InvalidValueObject(
                "a dose administered at the clinic says who supplied it",
                code="vaccination.supply_required",
            )
        if not given_here and self.supply is not None:
            raise InvalidValueObject(
                "only a dose administered at the clinic has a supplier",
                code="vaccination.supply_not_applicable",
            )
        if self.listed_fee is None:
            return
        check_fee(self.listed_fee)
        if self.supply is None or self.appointment_id is None:
            raise InvalidValueObject(
                "a dose is priced only when given in an appointment",
                code="vaccination.fee_needs_visit",
            )
        if self.supply == VaccineSupply.MINSAL and self.listed_fee.amount != 0:
            raise InvalidValueObject(
                "MINSAL vaccines are free of charge", code="vaccination.minsal_free"
            )

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    def void(self, by: UserId, reason: str, now: datetime) -> None:
        if self.is_voided:
            raise VaccinationAlreadyVoided(f"vaccination record {self.id} is already voided")
        reason = reason.strip()
        if not reason:
            raise InvalidValueObject("a reason is required to void a record",
                                     code="vaccination.void_reason_required")
        self.voided_at = now
        self.voided_by_id = by
        self.void_reason = reason
