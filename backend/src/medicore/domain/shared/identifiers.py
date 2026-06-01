"""Strongly-typed identifiers.

Identity is a UUID. Each aggregate gets its own ``*Id`` type so the type checker prevents
mixing, say, a ``PatientId`` where an ``AppointmentId`` is expected.

Human-readable codes shown in the UI (``P-00142``, ``A-2401``, ``REC-2026-0512-CR``) are a
*separate* concern: they live as a ``code`` field on the entity. Generating those sequential
codes requires coordination (per-tenant counters) and therefore belongs to the
application/infrastructure layers — the domain only stores and carries them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class Identifier:
    """Base UUID-backed identifier. Subclass per aggregate; do not use directly."""

    value: UUID = field(default_factory=uuid4)

    @classmethod
    def new(cls) -> Identifier:
        """Generate a fresh random identifier."""
        return cls(uuid4())

    @classmethod
    def parse(cls, raw: str | UUID) -> Identifier:
        """Build an identifier from a string or UUID.

        A malformed value raises ``InvalidValueObject`` (mapped to HTTP 422) instead of
        letting a raw ``ValueError`` bubble up as a 500.
        """
        if isinstance(raw, UUID):
            return cls(raw)
        try:
            return cls(UUID(str(raw)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidValueObject(f"Invalid {cls.__name__}: {raw!r}") from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TenantId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class LocationId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class UserId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class DoctorProfileId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class PatientId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class AppointmentId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class ConsultationId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class RecordId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class PrescriptionId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class DocumentId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class AvailabilityId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class ExceptionId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class NotificationId(Identifier):
    pass


@dataclass(frozen=True, slots=True)
class AuditLogId(Identifier):
    pass
