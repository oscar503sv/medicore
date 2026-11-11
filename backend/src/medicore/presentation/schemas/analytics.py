"""Practice metrics schemas. Money travels as a decimal string ("1234.50", USD); figures the
user may not see (income without ``analytics.money``) and sections above the clinic's
analytics tier come back as ``null``."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from medicore.domain.enums import AnalyticsTier


class PeriodResponse(BaseModel):
    kind: str
    start: date
    end: date
    previous_start: date
    previous_end: date


class TotalsResponse(BaseModel):
    booked: int
    attended: int
    no_shows: int
    cancelled: int
    no_show_rate: float | None
    cancellation_rate: float | None
    patients: int
    new_patients: int
    income: str | None


class DoctorRowResponse(BaseModel):
    doctor_id: str
    name: str
    totals: TotalsResponse


class TrendRowResponse(BaseModel):
    week: date
    attended: int
    income: str | None


class BreakdownRowResponse(BaseModel):
    key: str | None
    label: str | None
    attended: int
    income: str | None


class HeatCellResponse(BaseModel):
    weekday: int
    hour: int
    count: int


class ModuleActivityResponse(BaseModel):
    vaccinations: int | None
    applications: int | None
    procedures: int | None


class OperationsResponse(BaseModel):
    heatmap: list[HeatCellResponse]
    lead_times: dict[str, int]
    returning_patients: int
    modules: ModuleActivityResponse


class AnalyticsOverviewResponse(BaseModel):
    tier: AnalyticsTier
    scope: str
    doctor_id: str | None
    money: bool
    period: PeriodResponse
    current: TotalsResponse
    previous: TotalsResponse
    doctors: list[DoctorRowResponse] | None
    trend: list[TrendRowResponse] | None
    types: list[BreakdownRowResponse] | None
    insurers: list[BreakdownRowResponse] | None
    operations: OperationsResponse | None
