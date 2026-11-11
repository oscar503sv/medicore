"""MedicalCertificate aggregate — a constancia médica issued from a signed record.

Two kinds: proof that the patient was seen (``attendance``) or rest days (``rest``, the
private incapacidad). Once issued it never changes; a mistake is fixed by voiding it, with a
reason, and issuing another. The diagnosis only appears when the doctor chooses to disclose
it, and it is frozen as text so the paper and the system always agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from medicore.domain.enums import CertificateKind
from medicore.domain.shared.errors import InvalidStateTransition, InvalidValueObject
from medicore.domain.shared.identifiers import (
    CertificateId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)

MAX_REST_DAYS = 90
ADDRESSEE_MAX = 200
REMARKS_MAX = 1000
DIAGNOSIS_MAX = 1000
VOID_REASON_MAX = 500


def _clean(value: str | None, limit: int, code: str) -> str | None:
    text = (value or "").strip() or None
    if text and len(text) > limit:
        raise InvalidValueObject(f"{code}: text too long", code=code, max=limit)
    return text


@dataclass(slots=True)
class MedicalCertificate:
    id: CertificateId
    tenant_id: TenantId
    code: str  # "CM-2026-0007"
    patient_id: PatientId
    record_id: RecordId  # the visit it certifies
    doctor_id: UserId  # who issues and signs it: the record's author
    kind: CertificateKind
    issued_at: datetime
    rest_from: date | None = None
    rest_days: int | None = None
    diagnosis: str | None = None  # None: not disclosed
    remarks: str | None = None
    addressee: str | None = None  # None: "A quien corresponda"
    voided_at: datetime | None = None
    voided_by_id: UserId | None = None
    void_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.kind == CertificateKind.REST:
            if self.rest_from is None or self.rest_days is None:
                raise InvalidValueObject("rest days need a start date and a number of days",
                                         code="certificate.rest_required")
            if not 1 <= self.rest_days <= MAX_REST_DAYS:
                raise InvalidValueObject("rest days out of range",
                                         code="certificate.rest_days_range", max=MAX_REST_DAYS)
        else:
            self.rest_from = None
            self.rest_days = None
        self.diagnosis = _clean(self.diagnosis, DIAGNOSIS_MAX, "certificate.text_too_long")
        self.remarks = _clean(self.remarks, REMARKS_MAX, "certificate.text_too_long")
        self.addressee = _clean(self.addressee, ADDRESSEE_MAX, "certificate.text_too_long")

    @property
    def rest_until(self) -> date | None:
        """Last day of rest (inclusive)."""
        if self.rest_from is None or self.rest_days is None:
            return None
        return self.rest_from + timedelta(days=self.rest_days - 1)

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    def void(self, by_id: UserId, reason: str, now: datetime) -> None:
        if self.is_voided:
            raise InvalidStateTransition("MedicalCertificate", "voided", "voided")
        text = _clean(reason, VOID_REASON_MAX, "certificate.text_too_long")
        if not text:
            raise InvalidValueObject("say why the certificate is voided",
                                     code="certificate.void_reason_required")
        self.voided_at = now
        self.voided_by_id = by_id
        self.void_reason = text
