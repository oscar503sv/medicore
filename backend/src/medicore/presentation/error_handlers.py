"""Map domain and application errors to HTTP responses.

Every error body is ``{"detail": str, "code": str, "params": {...}}``:
- ``detail`` — English, human-readable (logs, API consumers; kept for compatibility);
- ``code`` — stable identifier the client translates (e.g. ``password.current_incorrect``);
- ``params`` — values to interpolate into the translated message.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import PurePath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from medicore.application.common.errors import (
    ApplicationError,
    AuthenticationFailed,
    EntityNotFound,
    TooManyLoginAttempts,
    ValidationError,
)
from medicore.application.use_cases.monitoring import (
    RecordServerError,
    RecordServerErrorCommand,
)
from medicore.domain.shared.errors import (
    CodedError,
    ConsultationNotSignable,
    DomainError,
    InvalidStateTransition,
    InvalidValueObject,
    PermissionDenied,
    QuotaExceeded,
    RecordAlreadySigned,
    SlotUnavailable,
)
from medicore.presentation.dependencies import get_clock, get_uow_factory

logger = logging.getLogger("medicore")


def _plain(value: Any) -> Any:
    return value if isinstance(value, str | int | float | bool) or value is None else str(value)


def _body(detail: Any, code: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "detail": detail,
        "code": code,
        "params": {k: _plain(v) for k, v in (params or {}).items()},
    }


def _json(status: int, exc: CodedError) -> JSONResponse:
    return JSONResponse(status_code=status, content=_body(str(exc), exc.code, exc.params))


def describe_exception(exc: BaseException) -> tuple[str, str]:
    """Exception class and innermost project frame ("use_cases/records.py:142 in execute"),
    falling back to the innermost frame when the error was raised outside the project.
    Only names and line numbers: the message may carry patient data."""
    kind = type(exc)
    error_type = kind.__qualname__ if kind.__module__ == "builtins" else (
        f"{kind.__module__}.{kind.__qualname__}"
    )
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "medicore" in PurePath(f.filename).parts]
    frame = (ours or frames)[-1] if frames else None
    if frame is None:
        return error_type, "unknown"
    parts = PurePath(frame.filename).parts
    if "medicore" in parts:
        parts = parts[len(parts) - parts[::-1].index("medicore"):]
    else:
        parts = parts[-2:]
    return error_type, f"{'/'.join(parts)}:{frame.lineno} in {frame.name}"


def _record_server_error(request: Request, exc: BaseException) -> None:
    """Keep the error for the platform console. Never raises: the database may be the
    very thing that failed, and the client must still get its 500."""
    route = request.scope.get("route")
    error_type, location = describe_exception(exc)
    overrides = request.app.dependency_overrides
    try:
        factory = overrides.get(get_uow_factory, get_uow_factory)()
        clock = overrides.get(get_clock, get_clock)()
        RecordServerError(factory, clock).execute(
            RecordServerErrorCommand(
                method=request.method,
                route=getattr(route, "path", None) or request.url.path,
                status=500,
                error_type=error_type,
                location=location,
            )
        )
    except Exception:
        logger.warning("Could not record the server error", exc_info=True)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        # ApiError carries a code; plain HTTPExceptions (404 route, 405…) get a generic one.
        code = getattr(exc, "code", None) or f"http.{exc.status_code}"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.detail, code, getattr(exc, "params", None)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError):
        # Same list-shaped ``detail`` as FastAPI's default, plus a code and the bad fields.
        errors = jsonable_encoder(exc.errors())
        fields = sorted({str(e["loc"][-1]) for e in errors if e.get("loc")})
        return JSONResponse(
            status_code=422,
            content=_body(errors, "request_invalid", {"fields": ", ".join(fields)}),
        )

    @app.exception_handler(AuthenticationFailed)
    async def handle_auth_failed(request: Request, exc: AuthenticationFailed):
        return _json(401, exc)

    @app.exception_handler(TooManyLoginAttempts)
    async def handle_login_throttled(request: Request, exc: TooManyLoginAttempts):
        response = _json(429, exc)
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(PermissionDenied)
    async def handle_permission_denied(request: Request, exc: PermissionDenied):
        return _json(403, exc)

    @app.exception_handler(EntityNotFound)
    async def handle_not_found(request: Request, exc: EntityNotFound):
        return _json(404, exc)

    @app.exception_handler(ValidationError)
    async def handle_validation(request: Request, exc: ValidationError):
        return _json(400, exc)

    @app.exception_handler(SlotUnavailable)
    async def handle_slot(request: Request, exc: SlotUnavailable):
        # The requested slot is not bookable (out of hours, overlapping, or breaks rules).
        # A conflict with the doctor's current availability/agenda → 409. (SPEC C.3)
        return _json(409, exc)

    @app.exception_handler(QuotaExceeded)
    async def handle_quota(request: Request, exc: QuotaExceeded):
        # The subscription has no room left: a conflict with the clinic's plan.
        return _json(409, exc)

    @app.exception_handler(InvalidStateTransition)
    async def handle_state_transition(request: Request, exc: InvalidStateTransition):
        return _json(422, exc)

    @app.exception_handler(ConsultationNotSignable)
    async def handle_not_signable(request: Request, exc: ConsultationNotSignable):
        return _json(422, exc)

    @app.exception_handler(RecordAlreadySigned)
    async def handle_signed(request: Request, exc: RecordAlreadySigned):
        return _json(409, exc)

    @app.exception_handler(InvalidValueObject)
    async def handle_invalid_vo(request: Request, exc: InvalidValueObject):
        return _json(422, exc)

    @app.exception_handler(DomainError)
    async def handle_domain(request: Request, exc: DomainError):
        return _json(422, exc)

    @app.exception_handler(ApplicationError)
    async def handle_application(request: Request, exc: ApplicationError):
        return _json(400, exc)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # Last-resort handler: log the full traceback server-side, return a generic message
        # so internal details never leak to the client. Specific handlers above and FastAPI's
        # HTTPException/validation handling take precedence over this catch-all.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        await run_in_threadpool(_record_server_error, request, exc)
        return JSONResponse(status_code=500, content=_body("Internal server error", "internal"))
