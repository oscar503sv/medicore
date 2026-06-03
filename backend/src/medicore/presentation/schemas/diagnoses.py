"""Diagnosis catalog schemas."""

from __future__ import annotations

from pydantic import BaseModel


class DiagnosisConfigResponse(BaseModel):
    version: str  # cie10 | cie11


class DiagnosisSuggestion(BaseModel):
    version: str
    code: str
    label: str
    billable: bool
    chapter: str | None = None
