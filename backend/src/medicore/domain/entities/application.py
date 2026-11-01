"""In-clinic medication applications ("aplicaciones"): injections, IV, nebulizations…

* ``ApplicationDraft`` — what a doctor indicates during a consultation; held inside the
  Consultation and turned into an ``ApplicationOrder`` when it is signed.
* ``ApplicationOrder`` — what has to be applied: a drug, dose and route, given
  ``doses_total`` times every ``interval_hours`` from ``starts_at`` (clinic wall-clock).
  Either *internal* (ordered by a doctor of the clinic) or *external* (a prescription from an
  outside doctor, identified by name and JVPM number — Junta de Vigilancia de la Profesión
  Médica).
* ``ApplicationRecord`` — one dose actually applied (or refused / contraindicated), with the
  post-application observation window. Clinical record semantics: never edited; a wrong
  entry is voided with a reason and stays in the history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOrderStatus,
    ApplicationOutcome,
    ApplicationRoute,
    ApplicationSite,
)
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    ConsultationId,
    PatientId,
    TenantId,
    UserId,
)

DEFAULT_OBSERVATION_MINUTES = 30
MAX_OBSERVATION_MINUTES = 240
MAX_DOSES = 30
MAX_INTERVAL_HOURS = 168  # weekly
_JVPM = re.compile(r"^\d{2,6}$")


class ApplicationOrderClosed(DomainError):
    code = "application.order_closed"


class ApplicationAlreadyVoided(DomainError):
    code = "application.already_voided"


class ObservationNotOpen(DomainError):
    code = "application.observation_not_open"


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


def _check_plan(dose: str, drug: str, doses_total: int, interval_hours: int | None,
                observation_minutes: int) -> None:
    if not drug.strip() or not dose.strip():
        raise InvalidValueObject("drug and dose are required", code="application.drug_required")
    if not 1 <= doses_total <= MAX_DOSES:
        raise InvalidValueObject(
            f"doses must be between 1 and {MAX_DOSES}",
            code="application.invalid_doses", max=MAX_DOSES,
        )
    if doses_total > 1 and not (interval_hours and 1 <= interval_hours <= MAX_INTERVAL_HOURS):
        raise InvalidValueObject(
            "several doses need an interval in hours",
            code="application.interval_required", max=MAX_INTERVAL_HOURS,
        )
    if not 0 <= observation_minutes <= MAX_OBSERVATION_MINUTES:
        raise InvalidValueObject(
            f"observation must be between 0 and {MAX_OBSERVATION_MINUTES} minutes",
            code="application.invalid_observation", max=MAX_OBSERVATION_MINUTES,
        )


@dataclass(frozen=True, slots=True)
class ApplicationDraft:
    """An application indicated during a consultation, issued as an order on signing."""

    drug: str
    dose: str
    route: ApplicationRoute
    doses_total: int = 1
    interval_hours: int | None = None
    observation_minutes: int = DEFAULT_OBSERVATION_MINUTES
    instructions: str | None = None

    def __post_init__(self) -> None:
        _check_plan(self.dose, self.drug, self.doses_total, self.interval_hours,
                    self.observation_minutes)


@dataclass(slots=True)
class ApplicationOrder:
    id: ApplicationOrderId
    tenant_id: TenantId
    patient_id: PatientId
    drug: str
    dose: str  # "1 g", "75 mg"
    route: ApplicationRoute
    source: ApplicationOrderSource
    starts_at: datetime  # first dose due — naive clinic wall-clock, like appointments
    created_by_id: UserId
    doses_total: int = 1
    interval_hours: int | None = None
    observation_minutes: int = DEFAULT_OBSERVATION_MINUTES
    instructions: str | None = None
    ordered_by_id: UserId | None = None  # internal: the clinic's doctor
    external_prescriber: str | None = None  # external: outside doctor's name…
    external_jvpm: str | None = None  # …and JVPM number
    consultation_id: ConsultationId | None = None
    status: ApplicationOrderStatus = ApplicationOrderStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled_at: datetime | None = None
    cancelled_by_id: UserId | None = None
    cancel_reason: str | None = None

    def __post_init__(self) -> None:
        self.drug = self.drug.strip()
        self.dose = self.dose.strip()
        self.instructions = _text(self.instructions)
        self.external_prescriber = _text(self.external_prescriber)
        self.external_jvpm = _text(self.external_jvpm)
        if self.doses_total == 1:
            self.interval_hours = None
        _check_plan(self.dose, self.drug, self.doses_total, self.interval_hours,
                    self.observation_minutes)
        if self.source == ApplicationOrderSource.INTERNAL and self.ordered_by_id is None:
            raise InvalidValueObject("an internal order needs its doctor",
                                     code="application.doctor_required")
        if self.source == ApplicationOrderSource.EXTERNAL:
            if not self.external_prescriber:
                raise InvalidValueObject("an external prescription needs the doctor's name",
                                         code="application.prescriber_required")
            if not self.external_jvpm or not _JVPM.match(self.external_jvpm):
                raise InvalidValueObject("the JVPM number must have 2 to 6 digits",
                                         code="application.invalid_jvpm")

    @property
    def is_open(self) -> bool:
        return self.status in (ApplicationOrderStatus.PENDING, ApplicationOrderStatus.IN_PROGRESS)

    def due_at(self, dose_number: int) -> datetime:
        return self.starts_at + timedelta(hours=(self.interval_hours or 0) * (dose_number - 1))

    def next_dose(self, settled: set[int]) -> int | None:
        """The first dose number without an active record, or None when all are settled."""
        return next((n for n in range(1, self.doses_total + 1) if n not in settled), None)

    def refresh(self, settled: set[int]) -> None:
        """Recompute the status from the dose numbers that have an active record."""
        if self.status == ApplicationOrderStatus.CANCELLED:
            return
        if self.next_dose(settled) is None:
            self.status = ApplicationOrderStatus.COMPLETED
        elif settled:
            self.status = ApplicationOrderStatus.IN_PROGRESS
        else:
            self.status = ApplicationOrderStatus.PENDING

    def cancel(self, by: UserId, reason: str, now: datetime) -> None:
        if not self.is_open:
            raise ApplicationOrderClosed(f"order {self.id} is {self.status}")
        reason = reason.strip()
        if not reason:
            raise InvalidValueObject("a reason is required to cancel an order",
                                     code="application.reason_required")
        self.status = ApplicationOrderStatus.CANCELLED
        self.cancelled_at = now
        self.cancelled_by_id = by
        self.cancel_reason = reason


@dataclass(slots=True)
class ApplicationRecord:
    id: ApplicationRecordId
    tenant_id: TenantId
    order_id: ApplicationOrderId
    patient_id: PatientId
    dose_number: int
    outcome: ApplicationOutcome
    recorded_at: datetime  # instant (UTC) the dose was applied / declined
    recorded_by_id: UserId
    lot: str | None = None
    lot_expiry: date | None = None
    site: ApplicationSite | None = None
    blood_pressure: str | None = None  # "120/80"
    temperature: float | None = None  # °C
    allergy_override: str | None = None  # why it was applied despite an allergy alert
    notes: str | None = None
    observe_until: datetime | None = None
    observation_closed_at: datetime | None = None
    observation_closed_by_id: UserId | None = None
    reaction: bool | None = None
    reaction_notes: str | None = None
    voided_at: datetime | None = None
    voided_by_id: UserId | None = None
    void_reason: str | None = None

    def __post_init__(self) -> None:
        self.lot = _text(self.lot)
        self.notes = _text(self.notes)
        self.blood_pressure = _text(self.blood_pressure)
        self.allergy_override = _text(self.allergy_override)
        if self.blood_pressure and not re.match(r"^\d{2,3}/\d{2,3}$", self.blood_pressure):
            raise InvalidValueObject("blood pressure must look like 120/80",
                                     code="vitals.invalid_blood_pressure")
        if self.temperature is not None and not 30 <= self.temperature <= 45:
            raise InvalidValueObject("temperature out of range",
                                     code="application.invalid_temperature")
        if self.outcome != ApplicationOutcome.APPLIED:
            self.lot = self.lot_expiry = self.site = self.observe_until = None

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    @property
    def observing(self) -> bool:
        """Applied and still waiting for the nurse to close the observation."""
        return (
            self.observe_until is not None
            and self.observation_closed_at is None
            and not self.is_voided
        )

    def close_observation(self, by: UserId, reaction: bool, notes: str | None,
                          now: datetime) -> None:
        if not self.observing:
            raise ObservationNotOpen(f"record {self.id} has no open observation")
        notes = _text(notes)
        if reaction and not notes:
            raise InvalidValueObject("describe the reaction",
                                     code="application.reaction_notes_required")
        self.observation_closed_at = now
        self.observation_closed_by_id = by
        self.reaction = reaction
        self.reaction_notes = notes

    def void(self, by: UserId, reason: str, now: datetime) -> None:
        if self.is_voided:
            raise ApplicationAlreadyVoided(f"application record {self.id} is already voided")
        reason = reason.strip()
        if not reason:
            raise InvalidValueObject("a reason is required to void a record",
                                     code="application.reason_required")
        self.voided_at = now
        self.voided_by_id = by
        self.void_reason = reason
