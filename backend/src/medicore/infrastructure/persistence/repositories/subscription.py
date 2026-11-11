"""SQLAlchemy repositories for the subscription catalog (platform-level)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.infrastructure.persistence.mappers.subscription import (
    addon_pricing_to_row,
    plan_to_row,
    to_addon_pricing,
    to_plan,
)
from medicore.infrastructure.persistence.models.subscription import AddonPricingModel, PlanModel

_PRICING_ROW = 1


class SqlPlanRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list(self, include_inactive: bool = True) -> list[Plan]:
        q = self._s.query(PlanModel).order_by(PlanModel.sort_order, PlanModel.code)
        if not include_inactive:
            q = q.filter(PlanModel.active.is_(True))
        return [to_plan(r) for r in q.all()]

    def get(self, code: str) -> Plan | None:
        row = self._s.get(PlanModel, code)
        return to_plan(row) if row else None

    def save(self, plan: Plan) -> None:
        row = self._s.get(PlanModel, plan.code)
        if row is None:
            row = PlanModel(code=plan.code)
            self._s.add(row)
        plan_to_row(plan, row)


class SqlAddonPricingRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self) -> AddonPricing:
        # Seeded by the migration that created the table.
        return to_addon_pricing(self._s.get(AddonPricingModel, _PRICING_ROW))

    def save(self, pricing: AddonPricing) -> None:
        row = self._s.get(AddonPricingModel, _PRICING_ROW)
        if row is None:
            row = AddonPricingModel(id=_PRICING_ROW)
            self._s.add(row)
        addon_pricing_to_row(pricing, row)
