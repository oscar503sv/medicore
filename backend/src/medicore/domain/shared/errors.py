"""Domain errors.

These represent violations of business rules / invariants. They are framework-agnostic;
the presentation layer is responsible for mapping them to transport-level errors (e.g. HTTP).
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain rule violations."""


class InvalidValueObject(DomainError):
    """A value object was constructed with values that break its invariants."""


class InvalidStateTransition(DomainError):
    """An aggregate was asked to transition between states in a way that is not allowed."""

    def __init__(self, entity: str, current: object, attempted: object) -> None:
        self.entity = entity
        self.current = current
        self.attempted = attempted
        super().__init__(
            f"{entity}: invalid transition from {current!r} to {attempted!r}"
        )


class RecordAlreadySigned(DomainError):
    """Attempted to mutate a signed (immutable) medical record."""


class ConsultationNotSignable(DomainError):
    """A consultation cannot be signed yet (e.g. minimum completeness not met)."""


class SlotUnavailable(DomainError):
    """An appointment slot is not bookable (out of hours, overlapping, or breaks rules)."""


class PermissionDenied(DomainError):
    """The actor's role does not allow the requested operation."""
