"""Platform console · Business: how the SaaS is doing and who is using it.

Revenue (MRR from the clinics that pay, what was collected), clinics by subscription status,
upcoming expirations (renewal is manual, so this is the to-do list), adoption (activity from
each clinic's audit trail) and clinics at a seat limit (upgrade candidates).

MRR counts only paying clinics: active, past any trial, with a paid-until date, and not yet
read-only. Trials, open-ended clinics (the public demo, courtesy accounts) and suspended
clinics bring no monthly revenue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.timezone import tenant_today
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.plan import CURRENCY, AddonPricing, Plan
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import Role, SubscriptionStatus, TenantStatus
from medicore.domain.repositories._support import Paging, TenantActivity
from medicore.domain.services.seat_usage import seat_usage
from medicore.domain.services.subscription_pricing import monthly_quote
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import PlanLimits

ACTIVE_DAYS = 7  # a clinic used Medicore this week
INACTIVE_DAYS = 14  # no activity for two weeks: churn risk
SIGNED_DAYS = 30
EXPIRING_DAYS = 30
TREND_WEEKS = 12

# Where a clinic stands, for the overview: its subscription status, or why it has none.
COMPLIMENTARY = "complimentary"  # open-ended, no payments expected
SUSPENDED = "suspended"


def _zero() -> Money:
    return Money(Decimal("0"), CURRENCY)


@dataclass(frozen=True, slots=True)
class ClinicBusinessRow:
    tenant_id: str
    legal_name: str
    slug: str
    standing: str  # SubscriptionStatus value, "complimentary" or "suspended"
    plan_code: str
    plan_name: str
    modules: tuple[str, ...]
    period_end: date | None
    days_left: int | None
    monthly: Money | None
    paying: bool
    usage: dict[str, int]  # doctors, support_users, locations
    limits: PlanLimits
    at_capacity: tuple[str, ...]  # the quotas that are full
    activity: TenantActivity


@dataclass(frozen=True, slots=True)
class PlanShare:
    code: str
    name: str
    clinics: int
    mrr: Money


@dataclass(frozen=True, slots=True)
class BusinessOverviewDTO:
    today: date
    mrr: Money
    unpriced: int  # paying clinics on a custom-quote plan without an agreed price
    collected_this_month: Money
    collected_last_month: Money
    by_standing: dict[str, int]
    by_plan: list[PlanShare]
    by_module: dict[str, int]
    active_clinics: int
    inactive_clinics: int
    at_capacity_clinics: int
    weekly_signed: list[tuple[date, int]]
    expiring: list[ClinicBusinessRow]
    clinics: list[ClinicBusinessRow] = field(default_factory=list)


def _standing(tenant: Tenant, today: date) -> str:
    if tenant.status != TenantStatus.ACTIVE:
        return SUSPENDED
    sub = tenant.subscription
    if sub.period_end is None and not sub.is_trial:
        return COMPLIMENTARY
    return str(sub.status(today))


def _full(usage: dict[str, int], limits: PlanLimits) -> tuple[str, ...]:
    quotas = {
        "doctors": limits.doctors,
        "support_users": limits.support_users,
        "locations": limits.locations,
    }
    return tuple(k for k, limit in quotas.items() if limit is not None and usage[k] >= limit)


def _sum(amounts) -> Money:
    total = _zero()
    for amount in amounts:
        total = total + amount
    return total


def _month_start(day: date, back: int = 0) -> date:
    year, month = day.year, day.month - back
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def _weeks(today: date, counts: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """Every one of the last TREND_WEEKS weeks (Mondays), zero when nothing was signed."""
    by_week = dict(counts)
    this_monday = today - timedelta(days=today.weekday())
    mondays = [this_monday - timedelta(weeks=n) for n in range(TREND_WEEKS - 1, -1, -1)]
    return [(m, by_week.get(m, 0)) for m in mondays]


class GetBusinessOverview:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, actor: PlatformActorContext) -> BusinessOverviewDTO:
        now: datetime = self._clock.now()
        today = now.date()
        with self._factory.platform_uow() as uow:
            tenants = [
                t for t in uow.tenants.list(paging=Paging(limit=1000)).items
                if t.status != TenantStatus.ARCHIVED
            ]
            plans: dict[str, Plan] = {p.code: p for p in uow.plans.list()}
            addons: AddonPricing = uow.addon_pricing.get()
        last_month = _month_start(today, 1)
        trend_since = today - timedelta(days=today.weekday(), weeks=TREND_WEEKS - 1)
        with self._factory.platform_reads() as reads:
            staff = reads.active_staff_by_tenant()
            payments = reads.payments_since(last_month)
            activity = reads.activity_by_tenant(
                now - timedelta(days=ACTIVE_DAYS), now - timedelta(days=SIGNED_DAYS)
            )
            weekly = reads.signed_per_week(datetime.combine(trend_since, now.timetz()))

        rows = [self._row(t, plans, addons, staff, activity) for t in tenants]
        rows.sort(key=lambda r: r.legal_name.lower())
        paying = [r for r in rows if r.paying]
        this_month = _month_start(today)

        by_plan: list[PlanShare] = []
        for plan in sorted(plans.values(), key=lambda p: p.sort_order):
            on_plan = [r for r in rows if r.plan_code == plan.code]
            if on_plan:
                by_plan.append(PlanShare(
                    plan.code, plan.name, len(on_plan),
                    _sum(r.monthly for r in on_plan if r.paying and r.monthly),
                ))

        by_standing: dict[str, int] = {}
        by_module: dict[str, int] = {}
        for r in rows:
            by_standing[r.standing] = by_standing.get(r.standing, 0) + 1
            for m in r.modules:
                by_module[m] = by_module.get(m, 0) + 1

        working = [r for r in rows if r.standing != SUSPENDED]
        active_since = now - timedelta(days=ACTIVE_DAYS)
        inactive_since = now - timedelta(days=INACTIVE_DAYS)
        expiring = sorted(
            (
                r for r in working
                if r.days_left is not None and r.days_left <= EXPIRING_DAYS
                and r.standing != str(SubscriptionStatus.READ_ONLY)
            ),
            key=lambda r: r.days_left,
        )
        return BusinessOverviewDTO(
            today=today,
            mrr=_sum(r.monthly for r in paying if r.monthly),
            unpriced=sum(1 for r in paying if r.monthly is None),
            collected_this_month=_sum(
                Money(p.amount, CURRENCY) for p in payments if p.paid_on >= this_month
            ),
            collected_last_month=_sum(
                Money(p.amount, CURRENCY) for p in payments if p.paid_on < this_month
            ),
            by_standing=by_standing,
            by_plan=by_plan,
            by_module=by_module,
            active_clinics=sum(
                1 for r in working
                if r.activity.last_activity and r.activity.last_activity >= active_since
            ),
            inactive_clinics=sum(
                1 for r in working
                if not r.activity.last_activity or r.activity.last_activity < inactive_since
            ),
            at_capacity_clinics=sum(1 for r in working if r.at_capacity),
            weekly_signed=_weeks(today, weekly),
            expiring=expiring,
            clinics=rows,
        )

    def _row(self, tenant, plans, addons, staff, activity) -> ClinicBusinessRow:
        today = tenant_today(tenant, self._clock)
        sub = tenant.subscription
        plan = plans.get(sub.plan_code)
        standing = _standing(tenant, today)
        by_role = {Role(role): n for role, n in staff.get(str(tenant.id), {}).items()}
        seats = seat_usage(by_role)
        usage = {
            "doctors": seats.doctors,
            "support_users": seats.support_users,
            "locations": len(tenant.locations),
        }
        limits = plan.limits.overridden_by(sub.limit_overrides) if plan else PlanLimits()
        paying = standing in (str(SubscriptionStatus.ACTIVE), str(SubscriptionStatus.GRACE))
        return ClinicBusinessRow(
            tenant_id=str(tenant.id),
            legal_name=tenant.legal_name,
            slug=str(tenant.slug),
            standing=standing,
            plan_code=sub.plan_code,
            plan_name=plan.name if plan else sub.plan_code,
            modules=tuple(sorted(str(m) for m in sub.modules)),
            period_end=sub.period_end,
            days_left=sub.days_left(today),
            monthly=monthly_quote(sub, plan, addons) if plan else None,
            paying=paying,
            usage=usage,
            limits=limits,
            at_capacity=_full(usage, limits),
            activity=activity.get(str(tenant.id), TenantActivity()),
        )
