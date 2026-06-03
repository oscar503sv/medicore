"""Deterministic fakes for the application ports."""

from __future__ import annotations

from datetime import date, datetime

from medicore.application.ports.token_issuer import SessionClaims
from medicore.domain.enums import ClinicalRecordType

_RECORD_SUFFIX = {
    ClinicalRecordType.CONSULTATION: "CO",
    ClinicalRecordType.PROCEDURE: "PR",
    ClinicalRecordType.MEDICATION_APPLICATION: "MA",
    ClinicalRecordType.VACCINATION: "VA",
    ClinicalRecordType.LAB_RESULT: "LR",
    ClinicalRecordType.IMAGING_RESULT: "IM",
    ClinicalRecordType.DISCHARGE_SUMMARY: "EP",
}


class FixedClock:
    """A clock that returns a fixed instant (mutable for time-travel in tests).

    Naive datetimes are used so they stay comparable with the slot resolver, which builds
    candidate slots with ``datetime.combine`` (also naive).
    """

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 5, 31, 9, 0)

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class PlainPasswordHasher:
    """Reversible 'hash' for tests only — never use in production."""

    PREFIX = "hashed:"

    def hash(self, plain: str) -> str:
        return f"{self.PREFIX}{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == self.hash(plain)


class FakeTokenIssuer:
    def issue(self, claims: SessionClaims) -> str:
        return (
            f"{claims.user_id}|{claims.tenant_id}|{claims.role}|{claims.scope}|"
            f"{claims.impersonator}"
        )

    def decode(self, token: str) -> SessionClaims:
        import jwt

        try:
            user_id, tenant_id, role, scope, imp = token.split("|")
        except ValueError as exc:
            raise jwt.DecodeError("invalid fake token format") from exc
        return SessionClaims(
            user_id=user_id,
            tenant_id=None if tenant_id == "None" else tenant_id,
            role=role,
            scope=scope,
            impersonator=None if imp == "None" else imp,
        )


class SequentialCodeGenerator:
    def __init__(self) -> None:
        self._patient = 141  # next → P-00142
        self._appointment = 2400  # next → A-2401
        self._record = 0

    def next_patient_code(self) -> str:
        self._patient += 1
        return f"P-{self._patient:05d}"

    def next_appointment_code(self) -> str:
        self._appointment += 1
        return f"A-{self._appointment}"

    def next_record_code(self, record_type: ClinicalRecordType, on: date) -> str:
        self._record += 1
        suffix = _RECORD_SUFFIX.get(record_type, "GN")
        return f"REC-{on.year}-{on.month:02d}{on.day:02d}-{suffix}"
