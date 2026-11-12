"""Report schemas. Each table carries its columns (key and kind) and its rows as lists of
JSON values: dates as ``YYYY-MM-DD``, times as ``HH:MM``, money as a two-decimal string,
counts and ages (months) as integers."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from medicore.domain.enums import AnalyticsTier


class ReportColumnResponse(BaseModel):
    key: str
    kind: str


class ReportTableResponse(BaseModel):
    columns: list[ReportColumnResponse]
    rows: list[list[str | int | bool | None]]


class ReportResponse(BaseModel):
    kind: str
    start: date
    end: date
    scope: str
    doctor_id: str | None
    money: bool
    tier: AnalyticsTier
    summary: ReportTableResponse
    detail: ReportTableResponse
