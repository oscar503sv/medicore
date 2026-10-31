"""Dashboard schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    day: date
    appointments_today: int | None
    appointments_delta_pct: int | None
    pending_today: int | None
    patients_total: int | None
    patients_delta_pct: int | None
    occupancy_pct: int | None
    occupancy_delta_pts: int | None
