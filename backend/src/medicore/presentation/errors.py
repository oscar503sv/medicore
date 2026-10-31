"""HTTP errors raised directly by the presentation layer (auth dependencies, routers).

Same contract as the domain/application errors: a stable ``code`` (+ ``params``) next to
the English ``detail``, so clients can translate. See ``error_handlers``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str, **params: Any) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.params = params
