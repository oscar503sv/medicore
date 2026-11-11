"""Minor procedures done at the clinic ("procedimientos"): sutures, wound care, drainages,
IUD insertion, Pap smears, ECGs, small biopsies…

* ``ProcedureType`` — the clinic's catalog entry: who may perform it (only a doctor, or a
  nurse too), whether it needs informed consent, the suggested follow-up and the note
  templates. Configured per clinic, preloaded with the common ones.
* ``ProcedureDraft`` — a procedure a doctor indicates during a consultation; held inside the
  Consultation and turned into a ``Procedure`` when it is signed.
* ``Procedure`` — one procedure for one patient, from the order to the signed note. Before:
  checklist (allergies reviewed, anticoagulants, fasting), consent signed on paper (who
  signed, relationship, witness — no file is uploaded) and vitals. The note (anesthesia,
  technique, findings, materials, complications, home care) is signed and then immutable:
  corrections are appended as amendments.

Fees: the catalog lists a price per type; each procedure keeps a copy of it next to what is
charged. A procedure indicated in a consultation may be *included in the consultation fee*
(not the norm, but it happens): it is then charged nothing. Only those may be included —
a walk-in or a procedure appointment has no consultation to be included in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from medicore.domain.enums import ProcedurePerformer, ProcedureSource, ProcedureStatus, Role
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.fee import ZERO, Charge, check_fee
from medicore.domain.value_objects.money import Money

MAX_FOLLOW_UP_DAYS = 365
_BP = re.compile(r"^\d{2,3}/\d{2,3}$")


class ProcedureClosed(DomainError):
    code = "procedure.closed"


class ProcedureNotCompleted(DomainError):
    code = "procedure.not_completed"


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


def _check_follow_up(days: int | None) -> None:
    if days is not None and not 1 <= days <= MAX_FOLLOW_UP_DAYS:
        raise InvalidValueObject(
            f"follow-up must be between 1 and {MAX_FOLLOW_UP_DAYS} days",
            code="procedure.invalid_follow_up", max=MAX_FOLLOW_UP_DAYS,
        )


def can_perform(performer: ProcedurePerformer, role: Role) -> bool:
    """A doctor performs any procedure; anyone else only those open to nursing."""
    return role == Role.DOCTOR or performer == ProcedurePerformer.DOCTOR_OR_NURSE


# ── catalog ───────────────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class ProcedureType:
    id: ProcedureTypeId
    tenant_id: TenantId
    name: str
    performer: ProcedurePerformer = ProcedurePerformer.DOCTOR
    requires_consent: bool = False
    follow_up_days: int | None = None  # suggested control, e.g. stitches out in 8 days
    takes_specimen: bool = False  # usually sends a sample to pathology (biopsy, Pap smear)
    technique_template: str | None = None
    instructions_template: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    price: Money | None = None  # None: no price set

    def __post_init__(self) -> None:
        check_fee(self.price)
        self.name = " ".join(self.name.split())
        if not self.name:
            raise InvalidValueObject("the procedure needs a name", code="procedure.name_required")
        _check_follow_up(self.follow_up_days)
        self.technique_template = _text(self.technique_template)
        self.instructions_template = _text(self.instructions_template)


def _charge(price: Money | None, included: bool) -> Charge:
    """A procedure's starting charge: the listed price, or nothing when it is included in
    the consultation fee."""
    if included:
        return Charge(listed=price, charged=ZERO)
    return Charge.at_list_price(price)


# ── consultation draft ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ProcedureDraft:
    """A procedure indicated during a consultation; the type's rules are frozen with it."""

    type_id: ProcedureTypeId
    type_name: str
    performer: ProcedurePerformer
    requires_consent: bool
    indication: str
    follow_up_days: int | None = None
    takes_specimen: bool = False
    price: Money | None = None
    included: bool = False  # included in the consultation fee: charged nothing

    def __post_init__(self) -> None:
        if not self.indication.strip():
            raise InvalidValueObject("the indication is required",
                                     code="procedure.indication_required")

    @classmethod
    def of(cls, kind: ProcedureType, indication: str, included: bool = False) -> ProcedureDraft:
        return cls(
            type_id=kind.id, type_name=kind.name, performer=kind.performer,
            requires_consent=kind.requires_consent, indication=indication.strip(),
            follow_up_days=kind.follow_up_days, takes_specimen=kind.takes_specimen,
            price=kind.price, included=included,
        )

    @property
    def charge(self) -> Charge:
        return _charge(self.price, self.included)


# ── procedure ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ProcedureAmendment:
    """A correction appended to a signed note (the original text is never changed)."""

    at: datetime
    by_id: UserId
    text: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProcedureProgress:
    """What the performer fills in before signing (checklist, vitals and the note).
    Every field replaces the stored one."""

    allergies_reviewed: bool = False
    anticoagulants: bool | None = None  # None = not asked / not applicable
    fasting: bool | None = None
    allergy_override: str | None = None
    bp_before: str | None = None
    hr_before: int | None = None
    spo2_before: int | None = None
    temp_before: float | None = None
    bp_after: str | None = None
    hr_after: int | None = None
    spo2_after: int | None = None
    temp_after: float | None = None
    anesthesia: str | None = None
    technique: str | None = None
    findings: str | None = None
    materials: str | None = None
    complications: str | None = None
    instructions: str | None = None
    specimen_sent: bool = False
    specimen_description: str | None = None

    def __post_init__(self) -> None:
        for bp in (self.bp_before, self.bp_after):
            if bp and not _BP.match(bp.strip()):
                raise InvalidValueObject("blood pressure must look like 120/80",
                                         code="vitals.invalid_blood_pressure")
        for t in (self.temp_before, self.temp_after):
            if t is not None and not 30 <= t <= 45:
                raise InvalidValueObject("temperature must be between 30 and 45 °C",
                                         code="application.invalid_temperature")
        for hr in (self.hr_before, self.hr_after):
            if hr is not None and not 20 <= hr <= 250:
                raise InvalidValueObject("heart rate out of range", code="procedure.invalid_vitals")
        for s in (self.spo2_before, self.spo2_after):
            if s is not None and not 50 <= s <= 100:
                raise InvalidValueObject("SpO2 out of range", code="procedure.invalid_vitals")


@dataclass(slots=True)
class Procedure:
    id: ProcedureId
    tenant_id: TenantId
    patient_id: PatientId
    type_id: ProcedureTypeId
    # The type's rules at the time of the order (the catalog may change later).
    type_name: str
    performer: ProcedurePerformer
    requires_consent: bool
    source: ProcedureSource
    indication: str
    ordered_by_id: UserId
    created_by_id: UserId
    follow_up_days: int | None = None
    takes_specimen: bool = False
    consultation_id: ConsultationId | None = None
    appointment_id: AppointmentId | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: ProcedureStatus = ProcedureStatus.PENDING
    # checklist
    allergies_reviewed: bool = False
    anticoagulants: bool | None = None
    fasting: bool | None = None
    allergy_override: str | None = None
    # consent, signed on paper
    consent_signer: str | None = None
    consent_relationship: str | None = None  # None = the patient signed
    consent_witness: str | None = None
    consent_at: datetime | None = None
    consent_by_id: UserId | None = None
    # vitals
    bp_before: str | None = None
    hr_before: int | None = None
    spo2_before: int | None = None
    temp_before: float | None = None
    bp_after: str | None = None
    hr_after: int | None = None
    spo2_after: int | None = None
    temp_after: float | None = None
    # note
    anesthesia: str | None = None
    technique: str | None = None
    findings: str | None = None
    materials: str | None = None
    complications: str | None = None
    instructions: str | None = None
    specimen_sent: bool = False
    specimen_description: str | None = None
    # signature
    started_at: datetime | None = None
    performed_at: datetime | None = None
    performed_by_id: UserId | None = None
    follow_up_on: date | None = None
    # cancellation
    cancelled_at: datetime | None = None
    cancelled_by_id: UserId | None = None
    cancel_reason: str | None = None
    amendments: list[ProcedureAmendment] = field(default_factory=list)
    # fee: the catalog price when it was ordered and what is charged
    charge: Charge = field(default_factory=Charge)
    fee_included: bool = False  # included in the consultation it was indicated in

    def __post_init__(self) -> None:
        self.indication = self.indication.strip()
        if not self.indication:
            raise InvalidValueObject("the indication is required",
                                     code="procedure.indication_required")
        _check_follow_up(self.follow_up_days)

    @classmethod
    def from_draft(
        cls, draft: ProcedureDraft, *, tenant_id: TenantId, patient_id: PatientId,
        ordered_by_id: UserId, consultation_id: ConsultationId, now: datetime,
    ) -> Procedure:
        return cls(
            id=ProcedureId.new(), tenant_id=tenant_id, patient_id=patient_id,
            type_id=draft.type_id, type_name=draft.type_name, performer=draft.performer,
            requires_consent=draft.requires_consent, source=ProcedureSource.CONSULTATION,
            indication=draft.indication, ordered_by_id=ordered_by_id,
            created_by_id=ordered_by_id, follow_up_days=draft.follow_up_days,
            takes_specimen=draft.takes_specimen, consultation_id=consultation_id,
            created_at=now, charge=draft.charge, fee_included=draft.included,
        )

    @property
    def is_open(self) -> bool:
        return self.status in (ProcedureStatus.PENDING, ProcedureStatus.IN_PROGRESS)

    @property
    def has_consent(self) -> bool:
        return self.consent_at is not None

    def _assert_open(self) -> None:
        if not self.is_open:
            raise ProcedureClosed(f"procedure {self.id} is {self.status}")

    def _touch(self, now: datetime) -> None:
        if self.status == ProcedureStatus.PENDING:
            self.status = ProcedureStatus.IN_PROGRESS
        if self.started_at is None:
            self.started_at = now

    def save_progress(self, p: ProcedureProgress, now: datetime) -> None:
        self._assert_open()
        self.allergies_reviewed = p.allergies_reviewed
        self.anticoagulants = p.anticoagulants
        self.fasting = p.fasting
        self.allergy_override = _text(p.allergy_override)
        for name in ("bp_before", "bp_after"):
            setattr(self, name, _text(getattr(p, name)))
        for name in ("hr_before", "spo2_before", "temp_before",
                     "hr_after", "spo2_after", "temp_after"):
            setattr(self, name, getattr(p, name))
        for name in ("anesthesia", "technique", "findings", "materials", "complications",
                     "instructions"):
            setattr(self, name, _text(getattr(p, name)))
        self.specimen_sent = p.specimen_sent
        self.specimen_description = _text(p.specimen_description) if p.specimen_sent else None
        self._touch(now)

    def record_consent(self, signer: str, relationship: str | None, witness: str,
                       by: UserId, now: datetime) -> None:
        """The patient (or their guardian) signed the paper form in front of a witness."""
        self._assert_open()
        signer, witness = signer.strip(), witness.strip()
        if not signer or not witness:
            raise InvalidValueObject("the consent needs who signed it and a witness",
                                     code="procedure.consent_incomplete")
        self.consent_signer = signer
        self.consent_relationship = _text(relationship)
        self.consent_witness = witness
        self.consent_at = now
        self.consent_by_id = by
        self._touch(now)

    def sign(self, by: UserId, now: datetime, today: date, allergy_clash: bool) -> None:
        """Close the note. Afterwards it is immutable (corrections are amendments)."""
        self._assert_open()
        if self.requires_consent and not self.has_consent:
            raise InvalidValueObject("this procedure needs the signed consent",
                                     code="procedure.consent_required")
        if not self.allergies_reviewed:
            raise InvalidValueObject("the patient's allergies must be reviewed",
                                     code="procedure.allergies_not_reviewed")
        if allergy_clash and not self.allergy_override:
            raise InvalidValueObject("the anesthesia clashes with the patient's allergies",
                                     code="procedure.allergy_conflict")
        if not self.technique:
            raise InvalidValueObject("describe the technique before signing",
                                     code="procedure.technique_required")
        if self.specimen_sent and not self.specimen_description:
            raise InvalidValueObject("describe the specimen sent to pathology",
                                     code="procedure.specimen_required")
        if not allergy_clash:
            self.allergy_override = None
        self.status = ProcedureStatus.COMPLETED
        self.performed_at = now
        self.performed_by_id = by
        if self.started_at is None:
            self.started_at = now
        self.follow_up_on = (
            today + timedelta(days=self.follow_up_days) if self.follow_up_days else None
        )

    def cancel(self, by: UserId, reason: str, now: datetime) -> None:
        self._assert_open()
        reason = reason.strip()
        if not reason:
            raise InvalidValueObject("a reason is required", code="procedure.reason_required")
        self.status = ProcedureStatus.CANCELLED
        self.cancelled_at = now
        self.cancelled_by_id = by
        self.cancel_reason = reason

    def set_fee(self, *, included: bool, charged: Money | None, note: str | None) -> None:
        """Change what the procedure is charged: include it in its consultation's fee, or
        charge an amount (a reason is needed when it differs from the listed price)."""
        if self.status == ProcedureStatus.CANCELLED:
            raise ProcedureClosed(f"procedure {self.id} is cancelled")
        if included:
            if self.consultation_id is None:
                raise DomainError(
                    "only a procedure indicated in a consultation can be included in its fee",
                    code="fee.included_needs_consultation",
                )
            self.charge = Charge(listed=self.charge.listed, charged=ZERO, note=note)
        else:
            if charged is None:
                raise InvalidValueObject("the amount is required", code="fee.invalid_amount")
            self.charge = self.charge.adjust(charged, note)
        self.fee_included = included

    def amend(self, by: UserId, text: str, reason: str, now: datetime) -> ProcedureAmendment:
        if self.status != ProcedureStatus.COMPLETED:
            raise ProcedureNotCompleted(f"procedure {self.id} is not signed")
        text, reason = text.strip(), reason.strip()
        if not text or not reason:
            raise InvalidValueObject("an amendment needs the correction and its reason",
                                     code="procedure.amendment_required")
        amendment = ProcedureAmendment(at=now, by_id=by, text=text, reason=reason)
        self.amendments.append(amendment)
        return amendment
