"""Map domain and application errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from medicore.application.common.errors import (
    ApplicationError,
    AuthenticationFailed,
    EntityNotFound,
    ValidationError,
)
from medicore.domain.shared.errors import (
    ConsultationNotSignable,
    DomainError,
    InvalidStateTransition,
    InvalidValueObject,
    PermissionDenied,
    RecordAlreadySigned,
    SlotUnavailable,
)


def _json(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationFailed)
    async def handle_auth_failed(request: Request, exc: AuthenticationFailed):
        return _json(401, str(exc))

    @app.exception_handler(PermissionDenied)
    async def handle_permission_denied(request: Request, exc: PermissionDenied):
        return _json(403, str(exc))

    @app.exception_handler(EntityNotFound)
    async def handle_not_found(request: Request, exc: EntityNotFound):
        return _json(404, str(exc))

    @app.exception_handler(ValidationError)
    async def handle_validation(request: Request, exc: ValidationError):
        return _json(400, str(exc))

    @app.exception_handler(SlotUnavailable)
    async def handle_slot(request: Request, exc: SlotUnavailable):
        # The requested slot is not bookable (out of hours, overlapping, or breaks rules).
        # A conflict with the doctor's current availability/agenda → 409. (SPEC C.3)
        return _json(409, str(exc))

    @app.exception_handler(InvalidStateTransition)
    async def handle_state_transition(request: Request, exc: InvalidStateTransition):
        return _json(422, str(exc))

    @app.exception_handler(ConsultationNotSignable)
    async def handle_not_signable(request: Request, exc: ConsultationNotSignable):
        return _json(422, str(exc))

    @app.exception_handler(RecordAlreadySigned)
    async def handle_signed(request: Request, exc: RecordAlreadySigned):
        return _json(409, str(exc))

    @app.exception_handler(InvalidValueObject)
    async def handle_invalid_vo(request: Request, exc: InvalidValueObject):
        return _json(422, str(exc))

    @app.exception_handler(DomainError)
    async def handle_domain(request: Request, exc: DomainError):
        return _json(422, str(exc))

    @app.exception_handler(ApplicationError)
    async def handle_application(request: Request, exc: ApplicationError):
        return _json(400, str(exc))
