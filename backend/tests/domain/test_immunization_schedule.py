"""Immunization status rules over El Salvador's national schedule."""

from __future__ import annotations

from datetime import date

from medicore.domain.enums import Sex, VaccinationOutcome
from medicore.domain.services.immunization import (
    SCHEDULE,
    VACCINES,
    DoseRecord,
    add_months,
    dose_states,
)

GIVEN = VaccinationOutcome.ADMINISTERED


def _by_key(birth, sex, today, records=()):
    return {s.dose.key: s for s in dose_states(birth, sex, today, records)}


def test_schedule_is_consistent():
    keys = [d.key for d in SCHEDULE]
    assert len(keys) == len(set(keys))
    assert all(d.vaccine in VACCINES for d in SCHEDULE)


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2025, 11, 15), 3) == date(2026, 2, 15)


def test_infant_timeline():
    birth = date(2026, 6, 1)
    states = _by_key(birth, Sex.FEMALE, date(2026, 8, 10), [
        DoseRecord("BCG-1", GIVEN, date(2026, 6, 1)),
    ])
    assert states["BCG-1"].status == "administered"
    assert states["HEPB_PED-1"].status == "not_applicable"  # newborn-only window (1 month)
    assert states["HEXA-1"].status == "due"  # due 1 Aug, inside the grace period
    assert states["HEXA-2"].status == "upcoming"  # due 1 Oct
    assert states["HEXA-2"].due_on == date(2026, 10, 1)
    assert states["SPR-1"].status == "upcoming"


def test_due_soon_window_and_overdue_after_grace():
    birth = date(2026, 1, 1)  # HEXA-1 due 1 Mar
    assert _by_key(birth, Sex.MALE, date(2026, 2, 15))["HEXA-1"].status == "due_soon"
    assert _by_key(birth, Sex.MALE, date(2026, 4, 15))["HEXA-1"].status == "overdue"


def test_adults_are_not_chased_for_childhood_doses():
    states = _by_key(date(1980, 5, 5), Sex.MALE, date(2026, 10, 31))
    for key in ("BCG-1", "HEXA-1", "SPR-2", "DPT-B2"):
        assert states[key].status == "not_applicable"
    assert states["TD-1"].status == "overdue"  # never recorded: booster pending
    assert "VPH-1" not in states  # female only
    assert states["INFLU-Y"].status == "upcoming"  # from 60


def test_periodic_dose_is_due_again_after_its_interval():
    birth = date(1960, 3, 1)
    today = date(2026, 10, 31)
    states = _by_key(birth, Sex.FEMALE, today, [
        DoseRecord("INFLU-Y", GIVEN, date(2025, 5, 2)),
        DoseRecord("TD-1", GIVEN, date(2020, 1, 1)),
    ])
    assert states["INFLU-Y"].status == "overdue"
    assert states["INFLU-Y"].due_on == date(2026, 5, 2)
    assert states["INFLU-Y"].last_on == date(2025, 5, 2)
    assert states["TD-1"].status == "upcoming"
    assert states["TD-1"].due_on == date(2030, 1, 1)


def test_refusal_settles_a_one_off_dose_and_a_later_dose_wins():
    birth = date(2026, 1, 1)
    today = date(2026, 6, 1)
    refused = DoseRecord("ROTA-1", VaccinationOutcome.REFUSED, date(2026, 3, 1))
    assert _by_key(birth, Sex.MALE, today, [refused])["ROTA-1"].status == "refused"
    given = DoseRecord("ROTA-1", GIVEN, date(2026, 3, 20))
    assert _by_key(birth, Sex.MALE, today, [refused, given])["ROTA-1"].status == "administered"


def test_refusing_the_yearly_flu_only_covers_that_season():
    birth = date(1950, 1, 1)
    refused = DoseRecord("INFLU-Y", VaccinationOutcome.REFUSED, date(2026, 4, 1))
    assert _by_key(birth, Sex.MALE, date(2026, 10, 1), [refused])["INFLU-Y"].status == "refused"
    assert _by_key(birth, Sex.MALE, date(2027, 6, 1), [refused])["INFLU-Y"].status == "overdue"


def test_non_routine_doses_are_indicated_not_overdue():
    states = _by_key(date(1990, 1, 1), Sex.FEMALE, date(2026, 10, 31))
    assert states["TDPA-P"].status == "indicated"
    assert states["HEPB_ADULT-1"].status == "indicated"


def test_periodic_childhood_dose_is_not_chased_past_its_age_limit():
    adult = dose_states(date(1985, 4, 12), Sex.FEMALE, date(2026, 5, 31), [])
    flu = next(s for s in adult if s.dose.key == "INFLU_PED-Y")
    assert flu.status == "not_applicable" and flu.due_on is None
