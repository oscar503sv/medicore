"""Analytics router: the clinic's practice metrics, shaped by its tier and the user's
metrics permissions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query

from medicore.application.use_cases.analytics import AnalyticsQuery, GetAnalyticsOverview
from medicore.domain.shared.identifiers import UserId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.analytics import AnalyticsOverviewResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _money(value):
    """Decimals (income) as two-decimal strings, recursively."""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return {k: _money(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_money(v) for v in value]
    return value


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def overview(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    period: str = Query(default="month", pattern="^(week|month|range)$"),
    start: date | None = None,
    end: date | None = None,
    doctor_id: str | None = None,
):
    query = AnalyticsQuery(
        period=period, start=start, end=end,
        doctor_id=UserId.parse(doctor_id) if doctor_id else None,
    )
    return _money(asdict(GetAnalyticsOverview(uow, clock).execute(actor, query)))
