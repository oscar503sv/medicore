"""Dashboard router: headline numbers for the home page."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from medicore.application.use_cases.dashboard import GetDashboardSummary
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.dashboard import DashboardSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def summary(actor: Actor, uow: UoW, clock: Clock):
    return DashboardSummaryResponse(**asdict(GetDashboardSummary(uow, clock).execute(actor)))
