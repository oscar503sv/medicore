"""Practice metrics: the pure aggregations behind the clinic's dashboard."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from medicore.domain.repositories._support import AppointmentFact, ProcedureFact
from medicore.domain.services import practice_metrics as pm

MAY = (datetime(2026, 5, 1), datetime(2026, 6, 1))


def fact(start: datetime, status: str = "completed", *, doctor: str = "d1", patient: str = "p1",
         charged: str | None = "30", kind: str = "consult", insurer: str | None = None,
         booked: datetime | None = None) -> AppointmentFact:
    return AppointmentFact(
        doctor_id=doctor, patient_id=patient, type=kind, status=status, scheduled_start=start,
        created_at=booked or start, insurer_id=insurer,
        charged=Decimal(charged) if charged is not None else None,
    )


def test_summary_counts_rates_and_income():
    facts = [
        fact(datetime(2026, 5, 4, 9), patient="p1"),
        fact(datetime(2026, 5, 5, 9), patient="p2", charged="0"),
        fact(datetime(2026, 5, 6, 9), "no_show", patient="p3"),
        fact(datetime(2026, 5, 7, 9), "cancelled", patient="p4"),
        fact(datetime(2026, 5, 28, 9), "scheduled", patient="p5"),
        fact(datetime(2026, 4, 30, 9), patient="p1"),  # outside the window
    ]
    procedures = [ProcedureFact("d1", datetime(2026, 5, 4, 10), Decimal("15")),
                  ProcedureFact("d1", datetime(2026, 5, 4, 11), None)]  # included: free
    s = pm.summarize(facts, procedures, {"p1": datetime(2026, 4, 30, 9),
                                         "p2": datetime(2026, 5, 5, 9)}, *MAY)
    assert (s.booked, s.attended, s.no_shows, s.cancelled) == (4, 2, 1, 1)
    assert (s.patients, s.new_patients) == (2, 1)  # p1 came first in April
    assert s.income == Decimal("45")
    assert s.no_show_rate == 33.3  # 1 of the 3 visits that were due
    assert s.cancellation_rate == 20.0  # 1 of 5 booked


def test_rates_are_none_without_a_base():
    s = pm.summarize([], [], {}, *MAY)
    assert (s.no_show_rate, s.cancellation_rate, s.income) == (None, None, Decimal("0"))


def test_per_doctor_splits_appointments_and_procedures():
    facts = [fact(datetime(2026, 5, 4, 9), doctor="d1"), fact(datetime(2026, 5, 4, 9), doctor="d2",
                                                             charged="50")]
    rows = pm.per_doctor(facts, [ProcedureFact("d2", datetime(2026, 5, 4), Decimal("10"))],
                         {}, *MAY)
    assert rows["d1"].income == Decimal("30")
    assert rows["d2"].income == Decimal("60")


def test_weekly_trend_is_zero_filled_and_ends_with_the_week_of_the_last_day():
    facts = [fact(datetime(2026, 5, 25, 9)), fact(datetime(2026, 5, 11, 9), "no_show")]
    trend = pm.weekly_trend(facts, [], date(2026, 5, 31), 3)
    assert [t.week for t in trend] == [date(2026, 5, 11), date(2026, 5, 18), date(2026, 5, 25)]
    assert [t.attended for t in trend] == [0, 0, 1]
    assert trend[2].income == Decimal("30")


def test_breakdowns_by_type_and_insurer():
    facts = [fact(datetime(2026, 5, 4, 9), insurer="i1"), fact(datetime(2026, 5, 5, 9)),
             fact(datetime(2026, 5, 6, 9), kind="follow_up", charged="15"),
             fact(datetime(2026, 5, 7, 9), "cancelled", insurer="i1")]
    assert [(b.key, b.attended) for b in pm.by_type(facts)] == [("consult", 2), ("follow_up", 1)]
    insurers = {b.key: (b.attended, b.income) for b in pm.by_insurer(facts)}
    assert insurers == {None: (2, Decimal("45")), "i1": (1, Decimal("30"))}


def test_heatmap_skips_cancelled():
    facts = [fact(datetime(2026, 5, 4, 9)), fact(datetime(2026, 5, 4, 9, 30), "no_show"),
             fact(datetime(2026, 5, 4, 10), "cancelled")]
    assert pm.heatmap(facts) == {(0, 9): 2}


def test_lead_times_by_bucket():
    day = datetime(2026, 5, 20, 9)
    facts = [fact(day, booked=datetime(2026, 5, 20, 8)), fact(day, booked=datetime(2026, 5, 18)),
             fact(day, booked=datetime(2026, 5, 1)), fact(day, "cancelled",
                                                          booked=datetime(2026, 5, 1))]
    assert pm.lead_times(facts) == {"same_day": 1, "1_2": 1, "3_7": 0, "8_14": 0, "15_plus": 1}


def test_returning_patients_were_seen_before_the_window():
    facts = [fact(datetime(2026, 5, 4, 9), patient="old"), fact(datetime(2026, 5, 5, 9),
                                                                patient="new")]
    first = {"old": datetime(2026, 1, 10), "new": datetime(2026, 5, 5, 9)}
    assert pm.returning_patients(facts, first, MAY[0]) == 1
