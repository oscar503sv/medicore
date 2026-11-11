"""Domain errors.

These represent violations of business rules / invariants. They are framework-agnostic;
the presentation layer is responsible for mapping them to transport-level errors (e.g. HTTP).

Every error carries a stable machine-readable ``code`` (a class default, overridable per
raise) and ``params`` for interpolation, so clients can show a message in the user's language
instead of the English ``str(exc)``, which stays for logs and API consumers.
"""

from __future__ import annotations

from typing import Any


class CodedError(Exception):
    """Mixin base: an exception with a stable ``code`` and interpolation ``params``."""

    code: str = "error"

    def __init__(self, message: str = "", *, code: str | None = None, **params: Any) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.params: dict[str, Any] = params


class DomainError(CodedError):
    """Base class for all domain rule violations."""

    code = "domain_error"


class InvalidValueObject(DomainError):
    """A value object was constructed with values that break its invariants."""

    code = "invalid_value"


class InvalidStateTransition(DomainError):
    """An aggregate was asked to transition between states in a way that is not allowed."""

    code = "invalid_transition"

    def __init__(self, entity: str, current: object, attempted: object) -> None:
        self.entity = entity
        self.current = current
        self.attempted = attempted
        super().__init__(
            f"{entity}: invalid transition from {current!r} to {attempted!r}",
            entity=entity.split(".")[0],
            current=str(current),
            attempted=str(attempted),
        )


class RecordAlreadySigned(DomainError):
    """Attempted to mutate a signed (immutable) medical record."""

    code = "record_signed"


class ConsultationNotSignable(DomainError):
    """A consultation cannot be signed yet (e.g. minimum completeness not met)."""

    code = "consultation_not_signable"


class SlotUnavailable(DomainError):
    """An appointment slot is not bookable (out of hours, overlapping, or breaks rules)."""

    code = "slot_unavailable"


class QuotaExceeded(DomainError):
    """The clinic's subscription has no room for another doctor, support user or site."""

    code = "plan.quota_exceeded"


class PermissionDenied(DomainError):
    """The actor's role does not allow the requested operation."""

    code = "permission_denied"
