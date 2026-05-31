"""Application-level errors (distinct from domain rule violations)."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base class for application-layer failures."""


class EntityNotFound(ApplicationError):
    def __init__(self, entity: str, identifier: object) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")


class AuthenticationFailed(ApplicationError):
    """Invalid organization, credentials, or inactive account."""


class ValidationError(ApplicationError):
    """A command failed input validation before reaching the domain."""
