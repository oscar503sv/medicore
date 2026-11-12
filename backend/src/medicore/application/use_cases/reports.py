"""Reports: the rows behind the clinic's metrics, to read on screen or export as CSV.

The same gates as the metrics apply (see ``analytics``):

* **Scope**: ``analytics.clinic`` sees the whole clinic (optionally one doctor),
  ``analytics.own`` only the doctor's own appointments, procedures they ordered and doses
  they recorded.
* **Money**: ``analytics.money`` adds the price columns; the income report requires it.
* **Tier**: the basic tier reports on the current or the previous month; from the clinic
  tier on, any range up to a year.
* **Modules**: the vaccination, procedures and applications reports come with their module.

Exporting needs ``reports.export`` as well and is audited (``report.exported``) with the
report, the period and the number of rows, never the rows themselves.

A report is two tables: a ``summary`` (one row per status, doctor, insurer, vaccine…) and
the ``detail`` rows. Columns carry a kind so the screen and the CSV format each value the
same way: ``text``, ``date``, ``time``, ``money``, ``count``, ``age`` (months), ``bool``,
or ``enum:<name>`` for a value the interface translates (an appointment type or status…).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from medicore.application.common.timezone import tenant_today
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.enums import AddonModule, AnalyticsTier, AppointmentStatus, Role
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.services.analytics_access import analytics_tier
from medicore.domain.services.immunization import SCHEDULE_BY_KEY, VACCINES
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import UserId

MAX_RANGE_DAYS = 366

APPOINTMENTS = "appointments"
INCOME = "income"
INSURERS = "insurers"
NO_SHOWS = "no_shows"
VACCINATIONS = "vaccinations"
PROCEDURES = "procedures"
APPLICATIONS = "applications"
REPORT_KINDS = (APPOINTMENTS, INCOME, INSURERS, NO_SHOWS, VACCINATIONS, PROCEDURES,
                APPLICATIONS)
REPORT_MODULES = {
    VACCINATIONS: AddonModule.VACCINATION,
    PROCEDURES: AddonModule.PROCEDURES,
    APPLICATIONS: AddonModule.APPLICATIONS,
}

# Age bands of the vaccination summary (months, upper bound exclusive), as the MINSAL
# monthly report groups doses.
AGE_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("age_lt1", 0, 12),
    ("age_1_4", 12, 60),
    ("age_5_9", 60, 120),
    ("age_10_19", 120, 240),
    ("age_20_59", 240, 720),
    ("age_60", 720, None),
)


@dataclass(frozen=True, slots=True)
class ReportQuery:
    kind: str
    start: date
    end: date  # inclusive
    doctor_id: UserId | None = None  # clinic scope only: narrow to one doctor


@dataclass(frozen=True, slots=True)
class ReportColumn:
    key: str
    kind: str = "text"


@dataclass(frozen=True, slots=True)
class ReportTable:
    columns: tuple[ReportColumn, ...]
    rows: list[tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class Report:
    kind: str
    start: date
    end: date
    scope: str  # clinic | own
    doctor_id: str | None
    money: bool
    tier: AnalyticsTier
    summary: ReportTable
    detail: ReportTable


def _cols(*specs: str) -> tuple[ReportColumn, ...]:
    """``"date:date"`` → ReportColumn("date", "date"); a bare key is text."""
    out = []
    for spec in specs:
        key, _, kind = spec.partition(":")
        out.append(ReportColumn(key, kind or "text"))
    return tuple(out)


def _months(born: date, on: date) -> int:
    months = (on.year - born.year) * 12 + on.month - born.month
    return months - 1 if on.day < born.day else months


def _band(months: int) -> str:
    for key, low, high in AGE_BANDS:
        if months >= low and (high is None or months < high):
            return key
    return AGE_BANDS[-1][0]


def dose_label(dose_key: str | None) -> str | None:
    """The scheme dose a record fulfils as a token the interface translates: ``dose:2``,
    ``booster:1``, ``single``, ``yearly`` or ``periodic:10`` (years). None outside the
    scheme."""
    dose = SCHEDULE_BY_KEY.get(dose_key) if dose_key else None
    if dose is None:
        return None
    kind = str(dose.kind)
    if kind in ("dose", "booster"):
        return f"{kind}:{dose.number}"
    if kind == "periodic":
        return f"periodic:{(dose.repeat_months or 0) // 12}"
    return kind


def _vaccine_order(code: str) -> int:
    codes = list(VACCINES)
    return codes.index(code) if code in codes else len(codes)


def _money(rows: list[Decimal | None]) -> Decimal:
    return sum((r for r in rows if r is not None), Decimal("0"))


class _Context:
    """What every report builder needs: the reads, names and the clinic's clock."""

    def __init__(self, uow: UnitOfWork, tz: ZoneInfo | None, naive_clock: bool,
                 user: UserId | None, money: bool) -> None:
        self.uow = uow
        self.tz = tz
        self.naive_clock = naive_clock
        self.user = user
        self.money = money
        self.users = {
            str(u.id): u.name
            for u in uow.users.list(UserFilter(), Paging(limit=1000)).items
        }
        self.insurers = {str(i.id): i.name for i in uow.insurers.list()}

    def name(self, user_id: str | None) -> str | None:
        return self.users.get(user_id) if user_id else None

    def instant(self, wall: datetime) -> datetime:
        """Clinic wall-clock as an instant; a naive clock (tests) keeps it naive."""
        if self.naive_clock or self.tz is None:
            return wall
        return wall.replace(tzinfo=self.tz)

    def local(self, moment: datetime) -> datetime:
        """An instant as clinic wall-clock (a naive value is wall-clock already)."""
        if moment.tzinfo is None or self.tz is None:
            return moment.replace(tzinfo=None)
        return moment.astimezone(self.tz).replace(tzinfo=None)


class _ReportBase:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _build(self, actor: ActorContext, query: ReportQuery) -> Report:
        if query.kind not in REPORT_KINDS:
            raise ValidationError(f"unknown report {query.kind}", code="report.unknown")
        clinic_scope = has_permission(actor, Permission.ANALYTICS_CLINIC)
        if not clinic_scope and not (
            has_permission(actor, Permission.ANALYTICS_OWN) and actor.role == Role.DOCTOR
        ):
            raise PermissionDenied("no access to reports", code="report.not_allowed")
        money = has_permission(actor, Permission.ANALYTICS_MONEY)
        if query.kind == INCOME and not money:
            raise PermissionDenied("the income report needs analytics.money",
                                   code="report.money_required")
        if query.end < query.start or (query.end - query.start).days + 1 > MAX_RANGE_DAYS:
            raise ValidationError("invalid report range", code="report.invalid_range",
                                  max=MAX_RANGE_DAYS)
        user = query.doctor_id if clinic_scope else actor.user_id

        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        module = REPORT_MODULES.get(query.kind)
        if module is not None and not tenant.subscription.has_module(module):
            raise PermissionDenied("the report's module is not contracted",
                                   code="report.module_required", module=str(module))
        plan = self._uow.plans.get(tenant.subscription.plan_code)
        if plan is None:
            raise EntityNotFound("Plan", tenant.subscription.plan_code)
        tier = analytics_tier(plan, tenant.subscription)
        if not tier.includes(AnalyticsTier.CLINIC):
            today = tenant_today(tenant, self._clock)
            earliest = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            if query.start < earliest:
                raise ValidationError("the plan reports on this month or the last one",
                                      code="report.range_not_in_plan")

        ctx = _Context(
            self._uow, ZoneInfo(tenant.timezone) if tenant.timezone else None,
            self._clock.now().tzinfo is None, user, money,
        )
        builder = {
            APPOINTMENTS: _appointments,
            INCOME: _income,
            INSURERS: _insurers,
            NO_SHOWS: _no_shows,
            VACCINATIONS: _vaccinations,
            PROCEDURES: _procedures,
            APPLICATIONS: _applications,
        }[query.kind]
        summary, detail = builder(ctx, query.start, query.end)
        return Report(
            kind=query.kind, start=query.start, end=query.end,
            scope="clinic" if clinic_scope else "own",
            doctor_id=str(user) if user else None, money=money, tier=tier,
            summary=summary, detail=detail,
        )


class GetReport(_ReportBase):
    """A report to read on screen."""

    def execute(self, actor: ActorContext, query: ReportQuery) -> Report:
        with self._uow:
            return self._build(actor, query)


class ExportReport(_ReportBase):
    """A report to download: needs ``reports.export`` and leaves an audit entry."""

    def execute(self, actor: ActorContext, query: ReportQuery, part: str = "detail") -> Report:
        ensure_permission(actor, Permission.REPORTS_EXPORT)
        if part not in ("detail", "summary"):
            raise ValidationError(f"unknown part {part}", code="report.unknown")
        with self._uow:
            report = self._build(actor, query)
            table = report.detail if part == "detail" else report.summary
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(), "report.exported", "Report", query.kind,
                report=query.kind, part=part, start=query.start.isoformat(),
                end=query.end.isoformat(), doctor_id=report.doctor_id, rows=len(table.rows),
            ))
            self._uow.commit()
            return report


# ── Builders: (summary, detail) ──────────────────────────────────────────────


def _wall_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def _appointments(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    rows = ctx.uow.reports.appointment_rows(lo, hi, ctx.user)
    money_cols = ("listed:money", "charged:money", "fee_note") if ctx.money else ()
    detail = ReportTable(
        _cols("date:date", "time:time", "code", "patient_code", "patient", "doctor",
              "type:enum:appointment_type", "status:enum:appointment_status", "insurer",
              *money_cols),
        [
            (r.scheduled_start.date(), r.scheduled_start.time(), r.code, r.patient_code,
             r.patient_name, ctx.name(r.doctor_id), r.type, r.status,
             ctx.insurers.get(r.insurer_id) if r.insurer_id else None,
             *((r.listed, r.charged, r.fee_note) if ctx.money else ()))
            for r in rows
        ],
    )
    counts = Counter(r.status for r in rows)
    order = [str(s) for s in AppointmentStatus]
    summary = ReportTable(
        _cols("status:enum:appointment_status", "appointments:count"),
        [(s, counts[s]) for s in sorted(counts, key=lambda s: order.index(s)
                                        if s in order else len(order))],
    )
    return summary, detail


def _income(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    visits = [r for r in ctx.uow.reports.appointment_rows(lo, hi, ctx.user)
              if r.status == AppointmentStatus.COMPLETED]
    procedures = ctx.uow.reports.procedure_rows(ctx.instant(lo), ctx.instant(hi), ctx.user)
    entries: list[tuple[datetime, tuple[Any, ...]]] = []
    per_doctor: dict[str, list] = defaultdict(lambda: [0, 0, Decimal("0")])
    for v in visits:
        entries.append((v.scheduled_start, (
            v.scheduled_start.date(), "visit", v.code, v.patient_code, v.patient_name,
            ctx.name(v.doctor_id), ctx.insurers.get(v.insurer_id) if v.insurer_id else None,
            v.listed, v.charged, v.fee_note,
        )))
        per_doctor[v.doctor_id][0] += 1
        per_doctor[v.doctor_id][2] += v.charged or Decimal("0")
    for p in procedures:
        when = ctx.local(p.performed_at)
        charged = Decimal("0.00") if p.included else p.charged
        entries.append((when, (
            when.date(), "procedure_included" if p.included else "procedure", p.type_name,
            p.patient_code, p.patient_name, ctx.name(p.ordered_by_id), None, p.listed,
            charged, None,
        )))
        per_doctor[p.ordered_by_id][1] += 1
        per_doctor[p.ordered_by_id][2] += charged or Decimal("0")
    entries.sort(key=lambda e: e[0])
    detail = ReportTable(
        _cols("date:date", "source:enum:income_source", "concept", "patient_code", "patient",
              "doctor", "insurer", "listed:money", "charged:money", "fee_note"),
        [row for _, row in entries],
    )
    summary = ReportTable(
        _cols("doctor", "visits:count", "procedures:count", "income:money"),
        sorted(
            ((ctx.name(d) or "—", n_v, n_p, total) for d, (n_v, n_p, total)
             in per_doctor.items()),
            key=lambda r: (-r[3], r[0]),
        ),
    )
    return summary, detail


def _insurers(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    attended = [r for r in ctx.uow.reports.appointment_rows(lo, hi, ctx.user)
                if r.status == AppointmentStatus.COMPLETED]
    insured = [r for r in attended if r.insurer_id]
    money_col = ("charged:money",) if ctx.money else ()
    detail = ReportTable(
        _cols("date:date", "insurer", "code", "patient_code", "patient", "doctor",
              "type:enum:appointment_type", *money_col),
        [
            (r.scheduled_start.date(), ctx.insurers.get(r.insurer_id, "—"), r.code,
             r.patient_code, r.patient_name, ctx.name(r.doctor_id), r.type,
             *((r.charged,) if ctx.money else ()))
            for r in sorted(insured, key=lambda r: (ctx.insurers.get(r.insurer_id, ""),
                                                    r.scheduled_start))
        ],
    )
    groups: dict[str | None, list] = defaultdict(list)
    for r in attended:
        groups[r.insurer_id].append(r)
    # Out-of-pocket visits (no insurer) come last, as ``None`` (the interface names it).
    ordered = sorted(groups.items(), key=lambda g: (g[0] is None, -len(g[1])))
    summary = ReportTable(
        _cols("insurer", "attended:count", *(("income:money",) if ctx.money else ())),
        [
            (ctx.insurers.get(key, "—") if key else None, len(rows),
             *((_money([r.charged for r in rows]),) if ctx.money else ()))
            for key, rows in ordered
        ],
    )
    return summary, detail


def _no_shows(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    rows = ctx.uow.reports.appointment_rows(lo, hi, ctx.user)
    missed = [r for r in rows
              if r.status in (AppointmentStatus.NO_SHOW, AppointmentStatus.CANCELLED)]
    detail = ReportTable(
        _cols("date:date", "time:time", "status:enum:appointment_status", "code",
              "patient_code", "patient", "phone", "doctor", "type:enum:appointment_type"),
        [
            (r.scheduled_start.date(), r.scheduled_start.time(), r.status, r.code,
             r.patient_code, r.patient_name, r.patient_phone, ctx.name(r.doctor_id), r.type)
            for r in missed
        ],
    )
    per_doctor: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        counts = per_doctor[r.doctor_id]
        counts[0] += 1
        if r.status == AppointmentStatus.NO_SHOW:
            counts[1] += 1
        elif r.status == AppointmentStatus.CANCELLED:
            counts[2] += 1
    summary = ReportTable(
        _cols("doctor", "booked:count", "no_shows:count", "cancelled:count"),
        sorted(((ctx.name(d) or "—", *c) for d, c in per_doctor.items()),
               key=lambda r: (-(r[2] + r[3]), r[0])),
    )
    return summary, detail


def _vaccinations(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    rows = ctx.uow.reports.vaccination_rows(start, end, ctx.user)
    detail = ReportTable(
        _cols("date:date", "patient_code", "patient", "sex:enum:sex", "age:age",
              "vaccine:vaccine", "dose:dose", "lot", "recorded_by"),
        [
            (r.occurred_on, r.patient_code, r.patient_name, r.patient_sex,
             _months(r.date_of_birth, r.occurred_on), r.vaccine_code, dose_label(r.dose_key),
             r.lot, ctx.name(r.recorded_by_id))
            for r in rows
        ],
    )
    bands = [key for key, _, _ in AGE_BANDS]
    grid: dict[tuple[str, str | None], Counter] = defaultdict(Counter)
    order: dict[tuple[str, str | None], int] = {}
    for r in rows:
        key = (r.vaccine_code, dose_label(r.dose_key))
        grid[key][_band(_months(r.date_of_birth, r.occurred_on))] += 1
        scheduled = SCHEDULE_BY_KEY.get(r.dose_key) if r.dose_key else None
        order[key] = scheduled.number if scheduled else 99
    summary = ReportTable(
        _cols("vaccine:vaccine", "dose:dose", *(f"{b}:count" for b in bands), "total:count"),
        [
            (vaccine, dose, *(c[b] for b in bands), sum(c.values()))
            for (vaccine, dose), c in sorted(
                grid.items(),
                key=lambda g: (_vaccine_order(g[0][0]), order[g[0]], g[0][1] or ""),
            )
        ],
    )
    return summary, detail


def _procedures(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    rows = ctx.uow.reports.procedure_rows(ctx.instant(lo), ctx.instant(hi), ctx.user)
    money_cols = ("listed:money", "charged:money") if ctx.money else ()
    detail = ReportTable(
        _cols("date:date", "procedure", "patient_code", "patient", "ordered_by",
              "performed_by", *money_cols, "included:bool"),
        [
            (ctx.local(r.performed_at).date(), r.type_name, r.patient_code, r.patient_name,
             ctx.name(r.ordered_by_id), ctx.name(r.performed_by_id),
             *((r.listed, Decimal("0.00") if r.included else r.charged)
               if ctx.money else ()),
             r.included)
            for r in rows
        ],
    )
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r.type_name].append(r)
    summary = ReportTable(
        _cols("procedure", "performed:count", *(("income:money",) if ctx.money else ())),
        [
            (name, len(items), *((_money([r.charged for r in items]),) if ctx.money else ()))
            for name, items in sorted(groups.items(), key=lambda g: (-len(g[1]), g[0]))
        ],
    )
    return summary, detail


def _applications(ctx: _Context, start: date, end: date) -> tuple[ReportTable, ReportTable]:
    lo, hi = _wall_bounds(start, end)
    rows = ctx.uow.reports.application_rows(ctx.instant(lo), ctx.instant(hi), ctx.user)
    detail = ReportTable(
        _cols("date:date", "time:time", "patient_code", "patient", "drug", "dose",
              "route:enum:application_route", "dose_number:count", "lot", "recorded_by"),
        [
            (ctx.local(r.recorded_at).date(), ctx.local(r.recorded_at).time(), r.patient_code,
             r.patient_name, r.drug, r.dose, r.route, r.dose_number, r.lot,
             ctx.name(r.recorded_by_id))
            for r in rows
        ],
    )
    counts = Counter(r.drug for r in rows)
    summary = ReportTable(
        _cols("drug", "doses:count"),
        sorted(counts.items(), key=lambda c: (-c[1], c[0])),
    )
    return summary, detail
