"""Practice metrics: the dashboard sections each clinic gets from its analytics tier.

Two independent gates decide what comes back:

* **The tier** (plan, or operations with the add-on) decides which sections exist:
  basic = this month against last month; clinic = any period, per-doctor table, 12-week
  trend, appointment types and insurers; operations = also the weekday × hour map, how far
  ahead patients book, returning patients and the contracted modules' activity. A section
  above the tier comes back as ``None`` (the page shows what the upgrade adds).
* **Permissions** decide the scope and the money: ``analytics.clinic`` sees every doctor
  (optionally one), ``analytics.own`` only the appointments where the user is the doctor,
  and ``analytics.money`` adds the income figures (otherwise they are ``None``).

Periods run up to today when they include it (week to date, month to date) and are
compared with the same number of days just before, so a half-gone month is not set against
a full one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, has_permission
from medicore.application.common.timezone import tenant_today
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.enums import AddonModule, AnalyticsTier, Role
from medicore.domain.repositories._support import Paging, ProcedureFact, UserFilter
from medicore.domain.services import practice_metrics as pm
from medicore.domain.services.analytics_access import analytics_tier
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import PatientId, UserId

MAX_RANGE_DAYS = 366
TREND_WEEKS = 12
PERIOD_KINDS = ("week", "month", "range")


@dataclass(frozen=True, slots=True)
class AnalyticsQuery:
    period: str = "month"  # week | month | range
    start: date | None = None  # range only
    end: date | None = None  # range only, inclusive
    doctor_id: UserId | None = None  # clinic scope only: narrow to one doctor


@dataclass(frozen=True, slots=True)
class Period:
    kind: str
    start: date
    end: date  # inclusive
    previous_start: date
    previous_end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def resolve_period(today: date, tier: AnalyticsTier, query: AnalyticsQuery) -> Period:
    """The window to show and the one to compare it with. The basic tier always gets the
    month to date."""
    kind = query.period if tier.includes(AnalyticsTier.CLINIC) else "month"
    if kind not in PERIOD_KINDS:
        raise ValidationError(f"unknown period {kind}", code="analytics.invalid_range")
    if kind == "range":
        start, end = query.start, query.end
        if start is None or end is None or end < start:
            raise ValidationError("a range needs a start and an end after it",
                                  code="analytics.invalid_range", max=MAX_RANGE_DAYS)
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise ValidationError("the range is too long", code="analytics.invalid_range",
                                  max=MAX_RANGE_DAYS)
        length = (end - start).days + 1
        return Period(kind, start, end, start - timedelta(days=length),
                      start - timedelta(days=1))
    if kind == "week":
        start = pm.week_start(today)
        previous_start = start - timedelta(weeks=1)
    else:
        start = today.replace(day=1)
        previous_start = (start - timedelta(days=1)).replace(day=1)
    elapsed = (today - start).days
    # Same number of days into the previous period (clamped to its last day).
    previous_end = min(previous_start + timedelta(days=elapsed), start - timedelta(days=1))
    return Period(kind, start, today, previous_start, previous_end)


@dataclass(frozen=True, slots=True)
class Totals:
    booked: int
    attended: int
    no_shows: int
    cancelled: int
    no_show_rate: float | None
    cancellation_rate: float | None
    patients: int
    new_patients: int
    income: Decimal | None  # None without analytics.money


@dataclass(frozen=True, slots=True)
class DoctorRow:
    doctor_id: str
    name: str
    totals: Totals


@dataclass(frozen=True, slots=True)
class TrendRow:
    week: date
    attended: int
    income: Decimal | None


@dataclass(frozen=True, slots=True)
class BreakdownRow:
    key: str | None  # appointment type, or insurer id (None: private)
    label: str | None  # insurer name (None for types and private visits)
    attended: int
    income: Decimal | None


@dataclass(frozen=True, slots=True)
class HeatCell:
    weekday: int  # 0 = Monday
    hour: int
    count: int


@dataclass(frozen=True, slots=True)
class ModuleActivity:
    vaccinations: int | None  # None: module not contracted
    applications: int | None
    procedures: int | None


@dataclass(frozen=True, slots=True)
class Operations:
    heatmap: list[HeatCell]
    lead_times: dict[str, int]  # see practice_metrics.LEAD_TIME_BUCKETS
    returning_patients: int  # attended in the period, first seen before it
    modules: ModuleActivity


@dataclass(frozen=True, slots=True)
class AnalyticsOverview:
    tier: AnalyticsTier
    scope: str  # own | clinic
    doctor_id: str | None  # the doctor shown (own scope, or a clinic filter)
    money: bool
    period: Period
    current: Totals
    previous: Totals
    # Clinic tier and above (None below it); ``doctors`` also needs the clinic scope.
    doctors: list[DoctorRow] | None
    trend: list[TrendRow] | None
    types: list[BreakdownRow] | None
    insurers: list[BreakdownRow] | None
    # Operations tier only.
    operations: Operations | None


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Wall-clock ``[start, end + 1 day)``."""
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


class GetAnalyticsOverview:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, query: AnalyticsQuery) -> AnalyticsOverview:
        clinic_scope = has_permission(actor, Permission.ANALYTICS_CLINIC)
        if not clinic_scope and not (
            has_permission(actor, Permission.ANALYTICS_OWN) and actor.role == Role.DOCTOR
        ):
            raise PermissionDenied("no access to metrics", code="analytics.not_allowed")
        money = has_permission(actor, Permission.ANALYTICS_MONEY)
        doctor = query.doctor_id if clinic_scope else actor.user_id

        with self._uow:
            tenant = self._uow.tenants.get_by_id(actor.tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", actor.tenant_id)
            plan = self._uow.plans.get(tenant.subscription.plan_code)
            if plan is None:
                raise EntityNotFound("Plan", tenant.subscription.plan_code)
            tier = analytics_tier(plan, tenant.subscription)
            tz = ZoneInfo(tenant.timezone) if tenant.timezone else None
            period = resolve_period(tenant_today(tenant, self._clock), tier, query)
            clinic_tier = tier.includes(AnalyticsTier.CLINIC)
            operations_tier = tier.includes(AnalyticsTier.OPERATIONS)

            fetch_start = period.previous_start
            if clinic_tier:
                trend_first = pm.week_start(period.end) - timedelta(weeks=TREND_WEEKS - 1)
                fetch_start = min(fetch_start, trend_first)
            lo, hi = _bounds(fetch_start, period.end)
            reads = self._uow.analytics
            appointments = [
                replace(a, created_at=self._local(a.created_at, tz))
                for a in reads.appointment_facts(lo, hi, doctor)
            ]
            procedures = [
                replace(p, performed_at=self._local(p.performed_at, tz))
                for p in reads.procedure_facts(self._instant(lo, tz), self._instant(hi, tz),
                                               doctor)
            ]
            patients = {PatientId.parse(a.patient_id) for a in appointments
                        if a.status == pm.COMPLETED}
            first_visits = {
                str(pid): when for pid, when in reads.first_visits(list(patients), doctor).items()
            }

            start, end = _bounds(period.start, period.end)
            prev_start, prev_end = _bounds(period.previous_start, period.previous_end)
            current = pm.summarize(appointments, procedures, first_visits, start, end)
            previous = pm.summarize(appointments, procedures, first_visits, prev_start, prev_end)
            in_period = [a for a in appointments if pm.within(a.scheduled_start, start, end)]

            doctors = trend = types = insurers = None
            operations = None
            if clinic_tier:
                if clinic_scope and doctor is None:
                    doctors = self._doctor_rows(
                        pm.per_doctor(appointments, procedures, first_visits, start, end), money
                    )
                trend = [
                    TrendRow(t.week, t.attended, t.income if money else None)
                    for t in pm.weekly_trend(appointments, procedures, period.end, TREND_WEEKS)
                ]
                types = [BreakdownRow(b.key, None, b.attended, b.income if money else None)
                         for b in pm.by_type(in_period)]
                insurers = self._insurer_rows(pm.by_insurer(in_period), money)
            if operations_tier:
                cells = sorted(pm.heatmap(in_period).items())
                operations = Operations(
                    heatmap=[HeatCell(d, h, n) for (d, h), n in cells],
                    lead_times=pm.lead_times(in_period),
                    returning_patients=pm.returning_patients(in_period, first_visits, start),
                    modules=self._modules(
                        tenant.subscription, period, procedures, start, end, tz, doctor
                    ),
                )

        return AnalyticsOverview(
            tier=tier,
            scope="clinic" if clinic_scope else "own",
            doctor_id=str(doctor) if doctor else None,
            money=money,
            period=period,
            current=self._totals(current, money),
            previous=self._totals(previous, money),
            doctors=doctors,
            trend=trend,
            types=types,
            insurers=insurers,
            operations=operations,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _local(moment: datetime, tz: ZoneInfo | None) -> datetime:
        """An instant as clinic wall-clock (a naive value is taken as wall-clock already)."""
        if moment.tzinfo is None or tz is None:
            return moment.replace(tzinfo=None)
        return moment.astimezone(tz).replace(tzinfo=None)

    def _instant(self, wall: datetime, tz: ZoneInfo | None) -> datetime:
        """Clinic wall-clock as an instant; a naive clock (tests) keeps it naive."""
        if self._clock.now().tzinfo is None or tz is None:
            return wall
        return wall.replace(tzinfo=tz)

    @staticmethod
    def _totals(s: pm.Summary, money: bool) -> Totals:
        return Totals(
            booked=s.booked, attended=s.attended, no_shows=s.no_shows, cancelled=s.cancelled,
            no_show_rate=s.no_show_rate, cancellation_rate=s.cancellation_rate,
            patients=s.patients, new_patients=s.new_patients,
            income=s.income if money else None,
        )

    def _doctor_rows(self, summaries: dict[str, pm.Summary], money: bool) -> list[DoctorRow]:
        names = {
            str(u.id): u.name
            for u in self._uow.users.list(
                UserFilter(role=str(Role.DOCTOR)), Paging(limit=1000)
            ).items
        }
        # Procedures a nurse registered directly are not anyone's practice: they count in
        # the clinic's totals, not as a row of the per-doctor table.
        rows = [DoctorRow(d, names[d], self._totals(s, money))
                for d, s in summaries.items() if d in names]
        return sorted(rows, key=lambda r: (-r.totals.attended, r.name))

    def _insurer_rows(self, groups: list[pm.Breakdown], money: bool) -> list[BreakdownRow]:
        names = {str(i.id): i.name for i in self._uow.insurers.list()}
        return [
            BreakdownRow(b.key, names.get(b.key, "—") if b.key else None, b.attended,
                         b.income if money else None)
            for b in groups
        ]

    def _modules(self, subscription, period: Period, procedures: list[ProcedureFact],
                 start: datetime, end: datetime, tz: ZoneInfo | None,
                 user: UserId | None) -> ModuleActivity:
        reads = self._uow.analytics
        has = subscription.has_module
        return ModuleActivity(
            vaccinations=reads.vaccinations_recorded(period.start, period.end, user)
            if has(AddonModule.VACCINATION) else None,
            applications=reads.applications_recorded(
                self._instant(start, tz), self._instant(end, tz), user)
            if has(AddonModule.APPLICATIONS) else None,
            procedures=sum(1 for p in procedures if pm.within(p.performed_at, start, end))
            if has(AddonModule.PROCEDURES) else None,
        )

