"""ErrorEvent — one unexpected server error (an HTTP 500), kept for the platform console.

Deliberately thin: where it happened (method, route template, code location) and what kind
of error it was. Never the exception message, request body or query values — those can
carry patient data. The full traceback stays in the server logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    id: UUID
    occurred_at: datetime
    method: str
    route: str  # route template ("/api/v1/patients/{patient_id}"), not the raw URL
    status: int
    error_type: str  # exception class, e.g. "sqlalchemy.exc.OperationalError"
    location: str  # innermost project frame, e.g. "use_cases/records.py:142 in execute"
