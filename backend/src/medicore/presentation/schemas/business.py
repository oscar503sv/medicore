"""Platform console · Business overview schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from medicore.presentation.schemas.subscriptions import PlanLimitsSchema


class ClinicBusinessResponse(BaseModel):
    tenant_id: str
    legal_name: str
    slug: str
    standing: str  # trial | active | grace | read_only | complimentary | suspended
    plan_code: str
    plan_name: str
    modules: list[str]
    period_end: date | None
    days_left: int | None
    monthly: str | None
    paying: bool
    usage: dict[str, int]
    limits: PlanLimitsSchema
    at_capacity: list[str]
    last_activity: datetime | None
    active_users: int
    signed_records: int


class PlanShareResponse(BaseModel):
    code: str
    name: str
    clinics: int
    mrr: str


class WeekCount(BaseModel):
    week: date
    count: int


class BusinessOverviewResponse(BaseModel):
    today: date
    mrr: str
    unpriced: int
    collected_this_month: str
    collected_last_month: str
    by_standing: dict[str, int]
    by_plan: list[PlanShareResponse]
    by_module: dict[str, int]
    active_clinics: int
    inactive_clinics: int
    at_capacity_clinics: int
    weekly_signed: list[WeekCount]
    expiring: list[ClinicBusinessResponse]
    clinics: list[ClinicBusinessResponse]
