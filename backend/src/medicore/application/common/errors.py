"""Application-level errors (distinct from domain rule violations)."""

from __future__ import annotations

import math
from datetime import datetime

from medicore.domain.shared.errors import CodedError


class ApplicationError(CodedError):
    """Base class for application-layer failures (carries ``code``/``params``, see
    ``medicore.domain.shared.errors``)."""

    code = "application_error"


class EntityNotFound(ApplicationError):
    code = "not_found"

    def __init__(self, entity: str, identifier: object) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}", entity=entity)


class AuthenticationFailed(ApplicationError):
    """Invalid organization, credentials, or inactive account — answered with HTTP 401.

    Only for "who are you" failures: a 401 makes the client drop its session. Bad input
    from an already authenticated user (e.g. a wrong current password) is a ValidationError.
    """

    code = "auth.failed"


class TooManyLoginAttempts(ApplicationError):
    """Login temporarily locked after repeated failures (HTTP 429 + Retry-After)."""

    code = "auth.too_many_attempts"

    def __init__(self, locked_until: datetime, now: datetime) -> None:
        self.retry_after_seconds = max(1, math.ceil((locked_until - now).total_seconds()))
        super().__init__(
            "too many failed login attempts; try again later",
            retry_after_seconds=self.retry_after_seconds,
        )


class ValidationError(ApplicationError):
    """A command failed input validation before reaching the domain."""

    code = "validation_error"
