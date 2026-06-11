"""Application-level errors (distinct from domain rule violations)."""

from __future__ import annotations

import math
from datetime import datetime


class ApplicationError(Exception):
    """Base class for application-layer failures."""


class EntityNotFound(ApplicationError):
    def __init__(self, entity: str, identifier: object) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")


class AuthenticationFailed(ApplicationError):
    """Invalid organization, credentials, or inactive account."""


class TooManyLoginAttempts(ApplicationError):
    """Login temporarily locked after repeated failures (HTTP 429 + Retry-After)."""

    def __init__(self, locked_until: datetime, now: datetime) -> None:
        self.retry_after_seconds = max(1, math.ceil((locked_until - now).total_seconds()))
        super().__init__("too many failed login attempts; try again later")


class ValidationError(ApplicationError):
    """A command failed input validation before reaching the domain."""
