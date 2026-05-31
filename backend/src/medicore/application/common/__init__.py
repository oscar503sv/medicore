"""Application common helpers: actor context, errors and permission checks."""

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import (
    ApplicationError,
    AuthenticationFailed,
    EntityNotFound,
    ValidationError,
)

__all__ = [
    "ActorContext",
    "ApplicationError",
    "AuthenticationFailed",
    "EntityNotFound",
    "ValidationError",
]
