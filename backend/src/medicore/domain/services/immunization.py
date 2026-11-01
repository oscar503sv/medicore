"""Immunization catalog, schedule and per-patient status.

The schedule follows El Salvador's national vaccination scheme (Esquema Nacional de
Vacunación, MINSAL) for childhood, adolescence and adults. It is national, not per clinic,
so it lives here as versioned data; only the doses actually given are stored. Display names
and disease lists are translated by the client from the vaccine ``code``.

IMPORTANT: ages and catch-up limits must be checked against the MINSAL guidelines in force
before clinical use; adjust the data below when the national scheme changes.

Status rules (pure, no I/O):
- A dose has a due date (birth + recommended age). Before it: ``upcoming`` (or ``due_soon``
  within ``DUE_SOON_DAYS``); from it, ``due`` during ``GRACE_DAYS``, then ``overdue``.
- Childhood doses carry a catch-up limit: past it without a record → ``not_applicable``
  (an adult isn't flagged for missing infant doses).
- Periodic doses (yearly influenza, Td every 10 years) are due again ``repeat_months`` after
  the last one given.
- Non-routine doses (pregnancy, risk groups) are ``indicated`` — listed, never overdue.
- A recorded refusal or contraindication is shown as such and stops the dose being chased.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from medicore.domain.enums import Sex, VaccinationOutcome, VaccineRoute

SCHEDULE_NAME = "sv-minsal"
DUE_SOON_DAYS = 30
GRACE_DAYS = 30

Stage = Literal["childhood", "adolescence", "adulthood", "indicated"]
DoseKind = Literal["dose", "booster", "single", "yearly", "periodic"]
DoseStatus = Literal[
    "administered",
    "refused",
    "contraindicated",
    "overdue",
    "due",
    "due_soon",
    "upcoming",
    "not_applicable",
    "indicated",
]


@dataclass(frozen=True, slots=True)
class Vaccine:
    code: str
    route: VaccineRoute
    in_schedule: bool = True  # False: available to record, but not part of the scheme


@dataclass(frozen=True, slots=True)
class ScheduledDose:
    key: str  # stable id stored on records, e.g. "HEXA-1"
    vaccine: str
    kind: DoseKind
    number: int
    age_months: int  # recommended age
    stage: Stage
    max_age_months: int | None = None  # catch-up limit
    repeat_months: int | None = None  # periodic doses
    routine: bool = True
    sex: Sex | None = None


Y = 12  # months per year, for readability below

VACCINES: dict[str, Vaccine] = {
    v.code: v
    for v in (
        Vaccine("BCG", VaccineRoute.INTRADERMAL),
        Vaccine("HEPB_PED", VaccineRoute.INTRAMUSCULAR),
        Vaccine("HEXA", VaccineRoute.INTRAMUSCULAR),
        Vaccine("ROTA", VaccineRoute.ORAL),
        Vaccine("PCV13", VaccineRoute.INTRAMUSCULAR),
        Vaccine("INFLU_PED", VaccineRoute.INTRAMUSCULAR),
        Vaccine("SPR", VaccineRoute.SUBCUTANEOUS),
        Vaccine("DPT", VaccineRoute.INTRAMUSCULAR),
        Vaccine("BOPV", VaccineRoute.ORAL),
        Vaccine("VPH", VaccineRoute.INTRAMUSCULAR),
        Vaccine("TD", VaccineRoute.INTRAMUSCULAR),
        Vaccine("TDPA", VaccineRoute.INTRAMUSCULAR),
        Vaccine("INFLU", VaccineRoute.INTRAMUSCULAR),
        Vaccine("PPSV23", VaccineRoute.INTRAMUSCULAR),
        Vaccine("HEPB_ADULT", VaccineRoute.INTRAMUSCULAR),
        Vaccine("COVID19", VaccineRoute.INTRAMUSCULAR),
        # Offered by private clinics, outside the national scheme.
        Vaccine("VARICELA", VaccineRoute.SUBCUTANEOUS, in_schedule=False),
        Vaccine("HEPA", VaccineRoute.INTRAMUSCULAR, in_schedule=False),
        Vaccine("MENINGO", VaccineRoute.INTRAMUSCULAR, in_schedule=False),
        Vaccine("FIEBRE_AMARILLA", VaccineRoute.SUBCUTANEOUS, in_schedule=False),
    )
}

SCHEDULE: tuple[ScheduledDose, ...] = (
    # ── Childhood ──────────────────────────────────────────────────────────────────────
    ScheduledDose("BCG-1", "BCG", "single", 1, 0, "childhood", max_age_months=12),
    ScheduledDose("HEPB_PED-1", "HEPB_PED", "single", 1, 0, "childhood", max_age_months=1),
    ScheduledDose("HEXA-1", "HEXA", "dose", 1, 2, "childhood", max_age_months=6 * Y),
    ScheduledDose("HEXA-2", "HEXA", "dose", 2, 4, "childhood", max_age_months=6 * Y),
    ScheduledDose("HEXA-3", "HEXA", "dose", 3, 6, "childhood", max_age_months=6 * Y),
    ScheduledDose("ROTA-1", "ROTA", "dose", 1, 2, "childhood", max_age_months=4),
    ScheduledDose("ROTA-2", "ROTA", "dose", 2, 4, "childhood", max_age_months=8),
    ScheduledDose("PCV13-1", "PCV13", "dose", 1, 2, "childhood", max_age_months=5 * Y),
    ScheduledDose("PCV13-2", "PCV13", "dose", 2, 4, "childhood", max_age_months=5 * Y),
    ScheduledDose("PCV13-B1", "PCV13", "booster", 1, 12, "childhood", max_age_months=5 * Y),
    ScheduledDose("INFLU_PED-1", "INFLU_PED", "dose", 1, 6, "childhood", max_age_months=5 * Y),
    ScheduledDose("INFLU_PED-2", "INFLU_PED", "dose", 2, 7, "childhood", max_age_months=5 * Y),
    ScheduledDose(
        "INFLU_PED-Y", "INFLU_PED", "yearly", 1, 18, "childhood",
        max_age_months=5 * Y, repeat_months=12,
    ),
    ScheduledDose("SPR-1", "SPR", "dose", 1, 12, "childhood", max_age_months=12 * Y),
    ScheduledDose("SPR-2", "SPR", "dose", 2, 18, "childhood", max_age_months=12 * Y),
    ScheduledDose("DPT-B1", "DPT", "booster", 1, 18, "childhood", max_age_months=7 * Y),
    ScheduledDose("BOPV-B1", "BOPV", "booster", 1, 18, "childhood", max_age_months=7 * Y),
    ScheduledDose("DPT-B2", "DPT", "booster", 2, 4 * Y, "childhood", max_age_months=7 * Y),
    ScheduledDose("BOPV-B2", "BOPV", "booster", 2, 4 * Y, "childhood", max_age_months=7 * Y),
    # ── Adolescence ────────────────────────────────────────────────────────────────────
    ScheduledDose(
        "VPH-1", "VPH", "single", 1, 9 * Y, "adolescence",
        max_age_months=15 * Y, sex=Sex.FEMALE,
    ),
    ScheduledDose("TD-1", "TD", "periodic", 1, 10 * Y, "adolescence", repeat_months=10 * Y),
    # ── Adulthood (≥ 60) ───────────────────────────────────────────────────────────────
    ScheduledDose("INFLU-Y", "INFLU", "yearly", 1, 60 * Y, "adulthood", repeat_months=12),
    ScheduledDose("PPSV23-1", "PPSV23", "single", 1, 60 * Y, "adulthood"),
    # ── By indication (pregnancy, risk groups, campaigns) ──────────────────────────────
    ScheduledDose("TDPA-P", "TDPA", "single", 1, 15 * Y, "indicated", routine=False,
                  sex=Sex.FEMALE),
    ScheduledDose("HEPB_ADULT-1", "HEPB_ADULT", "dose", 1, 18 * Y, "indicated", routine=False),
    ScheduledDose("HEPB_ADULT-2", "HEPB_ADULT", "dose", 2, 18 * Y, "indicated", routine=False),
    ScheduledDose("HEPB_ADULT-3", "HEPB_ADULT", "dose", 3, 18 * Y, "indicated", routine=False),
    ScheduledDose("COVID19-1", "COVID19", "dose", 1, 6, "indicated", routine=False),
)
SCHEDULE_BY_KEY: dict[str, ScheduledDose] = {d.key: d for d in SCHEDULE}


@dataclass(frozen=True, slots=True)
class DoseRecord:
    """The facts the status calculation needs from a stored (non-voided) record."""

    dose_key: str | None
    outcome: VaccinationOutcome
    on: date


@dataclass(frozen=True, slots=True)
class DoseState:
    dose: ScheduledDose
    status: DoseStatus
    due_on: date | None  # next due date (None once settled or not applicable)
    last_on: date | None  # date of the record that settled it / last periodic dose


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def applies_to(dose: ScheduledDose, sex: Sex) -> bool:
    return dose.sex is None or dose.sex == sex


def _timing(due: date, today: date) -> DoseStatus:
    if today < due - timedelta(days=DUE_SOON_DAYS):
        return "upcoming"
    if today < due:
        return "due_soon"
    if today <= due + timedelta(days=GRACE_DAYS):
        return "due"
    return "overdue"


_OUTCOME_STATUS: dict[VaccinationOutcome, DoseStatus] = {
    VaccinationOutcome.ADMINISTERED: "administered",
    VaccinationOutcome.REFUSED: "refused",
    VaccinationOutcome.CONTRAINDICATED: "contraindicated",
}


def dose_states(
    birth: date, sex: Sex, today: date, records: Iterable[DoseRecord]
) -> list[DoseState]:
    """Status of every scheduled dose that applies to the patient, in schedule order."""
    by_key: dict[str, list[DoseRecord]] = {}
    for r in records:
        if r.dose_key:
            by_key.setdefault(r.dose_key, []).append(r)

    states: list[DoseState] = []
    for dose in SCHEDULE:
        if applies_to(dose, sex):
            mine = sorted(by_key.get(dose.key, []), key=lambda r: r.on)
            states.append(_state(dose, birth, today, mine))
    return states


def _state(dose: ScheduledDose, birth: date, today: date, mine: list[DoseRecord]) -> DoseState:
    last = mine[-1] if mine else None
    limit = add_months(birth, dose.max_age_months) if dose.max_age_months else None

    if dose.repeat_months:
        # Each record (given or not) settles one cycle; the next is due a period later.
        start = add_months(birth, dose.age_months)
        due = add_months(last.on, dose.repeat_months) if last else start
        given = [r for r in mine if r.outcome == VaccinationOutcome.ADMINISTERED]
        last_given = given[-1].on if given else None
        if limit and (due > limit or today > limit):  # the age window has closed
            return DoseState(dose, "administered" if given else "not_applicable", None, last_given)
        if last and last.outcome != VaccinationOutcome.ADMINISTERED and today < due:
            return DoseState(dose, _OUTCOME_STATUS[last.outcome], due, last.on)
        if not dose.routine and not mine:
            return DoseState(dose, "indicated", None, None)
        return DoseState(dose, _timing(due, today), due, last_given)

    if last:  # one-off dose already settled; a dose given wins over a later refusal
        given = [r for r in mine if r.outcome == VaccinationOutcome.ADMINISTERED]
        settled = given[-1] if given else last
        return DoseState(dose, _OUTCOME_STATUS[settled.outcome], None, settled.on)
    if not dose.routine:
        return DoseState(dose, "indicated", None, None)
    if limit and today > limit:
        return DoseState(dose, "not_applicable", None, None)
    due = add_months(birth, dose.age_months)
    return DoseState(dose, _timing(due, today), due, None)
