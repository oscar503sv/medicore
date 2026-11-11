"""Practice metrics: pure aggregations over appointment and procedure facts.

"Attended" means a completed appointment; the no-show rate is taken over the visits that
were due (attended + no-show), the cancellation rate over everything booked. Income is the
"estimated income": what attended visits and completed procedures were charged (not money
collected). Every datetime here is clinic wall-clock (naive).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from medicore.domain.repositories._support import AppointmentFact, ProcedureFact

COMPLETED = "completed"
NO_SHOW = "no_show"
CANCELLED = "cancelled"
ZERO = Decimal("0")

# Days between booking and the visit: (label, lowest day, highest day or None).
LEAD_TIME_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("same_day", 0, 0),
    ("1_2", 1, 2),
    ("3_7", 3, 7),
    ("8_14", 8, 14),
    ("15_plus", 15, None),
)


def _pct(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part * 100 / whole, 1)


def _charged(amount: Decimal | None) -> Decimal:
    return amount if amount is not None else ZERO


@dataclass(frozen=True, slots=True)
class Summary:
    booked: int  # not cancelled (attended, no-show, still to come)
    attended: int
    no_shows: int
    cancelled: int
    new_patients: int  # first attended visit (in scope) inside the window
    patients: int  # distinct patients attended
    income: Decimal  # attended visits + completed procedures

    @property
    def no_show_rate(self) -> float | None:
        return _pct(self.no_shows, self.attended + self.no_shows)

    @property
    def cancellation_rate(self) -> float | None:
        return _pct(self.cancelled, self.booked + self.cancelled)


def within(moment: datetime, start: datetime, end: datetime) -> bool:
    return start <= moment < end


def summarize(
    appointments: Iterable[AppointmentFact],
    procedures: Iterable[ProcedureFact],
    first_visits: dict[str, datetime],
    start: datetime,
    end: datetime,
) -> Summary:
    """Figures of the facts falling in ``[start, end)``. ``first_visits`` maps patient id →
    first attended visit, to tell new patients from returning ones."""
    statuses: Counter[str] = Counter()
    attended_patients: set[str] = set()
    income = ZERO
    for a in appointments:
        if not within(a.scheduled_start, start, end):
            continue
        statuses[a.status] += 1
        if a.status == COMPLETED:
            attended_patients.add(a.patient_id)
            income += _charged(a.charged)
    for p in procedures:
        if within(p.performed_at, start, end):
            income += _charged(p.charged)
    new = sum(
        1 for pid in attended_patients
        if pid in first_visits and within(first_visits[pid], start, end)
    )
    cancelled = statuses[CANCELLED]
    return Summary(
        booked=sum(statuses.values()) - cancelled,
        attended=statuses[COMPLETED],
        no_shows=statuses[NO_SHOW],
        cancelled=cancelled,
        new_patients=new,
        patients=len(attended_patients),
        income=income,
    )


def per_doctor(
    appointments: list[AppointmentFact],
    procedures: list[ProcedureFact],
    first_visits: dict[str, datetime],
    start: datetime,
    end: datetime,
) -> dict[str, Summary]:
    """``summarize`` for each doctor with any appointment or procedure in the window.
    A new patient is new to the clinic (``first_visits`` is clinic-wide)."""
    doctors = {a.doctor_id for a in appointments if within(a.scheduled_start, start, end)}
    doctors |= {p.doctor_id for p in procedures if within(p.performed_at, start, end)}
    return {
        d: summarize(
            [a for a in appointments if a.doctor_id == d],
            [p for p in procedures if p.doctor_id == d],
            first_visits, start, end,
        )
        for d in doctors
    }


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True, slots=True)
class TrendPoint:
    week: date  # Monday
    attended: int
    income: Decimal


def weekly_trend(
    appointments: Iterable[AppointmentFact],
    procedures: Iterable[ProcedureFact],
    last_day: date,
    weeks: int,
) -> list[TrendPoint]:
    """Attended visits and income per week, for ``weeks`` weeks ending with the week of
    ``last_day`` (zero-filled)."""
    first = week_start(last_day) - timedelta(weeks=weeks - 1)
    attended: Counter[date] = Counter()
    income: defaultdict[date, Decimal] = defaultdict(lambda: ZERO)
    for a in appointments:
        if a.status == COMPLETED:
            w = week_start(a.scheduled_start.date())
            attended[w] += 1
            income[w] += _charged(a.charged)
    for p in procedures:
        income[week_start(p.performed_at.date())] += _charged(p.charged)
    return [
        TrendPoint(w, attended[w], income[w])
        for w in (first + timedelta(weeks=n) for n in range(weeks))
    ]


@dataclass(frozen=True, slots=True)
class Breakdown:
    key: str | None
    attended: int
    income: Decimal


def _breakdown(appointments: Iterable[AppointmentFact], key) -> list[Breakdown]:
    attended: Counter = Counter()
    income: defaultdict = defaultdict(lambda: ZERO)
    for a in appointments:
        if a.status == COMPLETED:
            k = key(a)
            attended[k] += 1
            income[k] += _charged(a.charged)
    return sorted(
        (Breakdown(k, attended[k], income[k]) for k in attended),
        key=lambda b: (-b.attended, str(b.key)),
    )


def by_type(appointments: Iterable[AppointmentFact]) -> list[Breakdown]:
    return _breakdown(appointments, lambda a: a.type)


def by_insurer(appointments: Iterable[AppointmentFact]) -> list[Breakdown]:
    """None groups the private (out-of-pocket) visits."""
    return _breakdown(appointments, lambda a: a.insurer_id)


def heatmap(appointments: Iterable[AppointmentFact]) -> dict[tuple[int, int], int]:
    """Booked (not cancelled) appointments per (weekday 0=Monday, hour)."""
    cells: Counter[tuple[int, int]] = Counter()
    for a in appointments:
        if a.status != CANCELLED:
            cells[(a.scheduled_start.weekday(), a.scheduled_start.hour)] += 1
    return dict(cells)


def lead_times(appointments: Iterable[AppointmentFact]) -> dict[str, int]:
    """How far ahead the (not cancelled) appointments were booked. ``created_at`` must
    already be clinic wall-clock."""
    counts = dict.fromkeys((label for label, _, _ in LEAD_TIME_BUCKETS), 0)
    for a in appointments:
        if a.status == CANCELLED:
            continue
        days = max(0, (a.scheduled_start.date() - a.created_at.date()).days)
        for label, low, high in LEAD_TIME_BUCKETS:
            if days >= low and (high is None or days <= high):
                counts[label] += 1
                break
    return counts


def returning_patients(
    appointments: Iterable[AppointmentFact], first_visits: dict[str, datetime], start: datetime
) -> int:
    """Distinct attended patients whose first visit was before ``start``."""
    return len({
        a.patient_id for a in appointments
        if a.status == COMPLETED and a.patient_id in first_visits
        and first_visits[a.patient_id] < start
    })
