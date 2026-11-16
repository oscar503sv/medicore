"""Vaccination income in reports and metrics: named after the agenda, MINSAL at $0."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from medicore.application.common.permissions import ROLE_PERMISSIONS, Permission
from medicore.application.use_cases.analytics import AnalyticsQuery, GetAnalyticsOverview
from medicore.application.use_cases.reports import GetReport, ReportQuery
from medicore.domain.enums import VaccineSupply
from tests.application.test_vaccination_visit import _agenda, _appointment, _uow, _visit
from tests.application.test_vaccine_prices import _dose, _set
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock

TODAY = date(2026, 5, 31)  # FixedClock default


@pytest.fixture
def clinic():
    seed = seed_clinic()
    return seed, _agenda(seed)


def _admin(seed):
    actor = seed.actor(seed.admin)
    return replace(actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[actor.role] | {Permission.ANALYTICS_MONEY}))


def _income(seed):
    return GetReport(_uow(seed), FixedClock()).execute(
        _admin(seed), ReportQuery("income", TODAY, TODAY)
    )


def _overview(seed):
    return GetAnalyticsOverview(_uow(seed), FixedClock()).execute(
        _admin(seed), AnalyticsQuery(start=TODAY, end=TODAY)
    )


def test_income_report_names_the_agenda_and_the_vaccination_source(clinic):
    seed, agenda = clinic
    _set(seed, "TD", "25")
    _visit(seed, _appointment(seed, agenda), _dose("TD"), _dose("INFLU", VaccineSupply.MINSAL))

    report = _income(seed)

    keys = [c.key for c in report.detail.columns]
    (row,) = report.detail.rows
    assert row[keys.index("source")] == "vaccination"
    assert row[keys.index("doctor")] == "Vacunatorio"
    assert row[keys.index("charged")] == Decimal("25.00")
    assert [c.key for c in report.summary.columns][-2:] == ["vaccinations", "income"]
    assert report.summary.rows == [("Vacunatorio", 0, 0, 1, Decimal("25.00"))]


def test_metrics_count_the_vaccination_income_but_the_agenda_is_no_doctor(clinic):
    seed, agenda = clinic
    _set(seed, "TD", "25")
    _visit(seed, _appointment(seed, agenda), _dose("TD"))

    overview = _overview(seed)

    assert overview.current.income == Decimal("25.00")
    assert overview.types is not None
    assert next(t for t in overview.types if t.key == "vaccination").income == Decimal("25.00")
    assert all(d.doctor_id != str(agenda.id) for d in overview.doctors or [])


def test_a_minsal_only_visit_adds_zero(clinic):
    seed, agenda = clinic
    _visit(seed, _appointment(seed, agenda), _dose("TD", VaccineSupply.MINSAL))

    assert _overview(seed).current.income == Decimal("0.00")


def test_a_doctors_own_vaccination_visit_counts_in_their_scope(clinic):
    seed, _ = clinic
    _set(seed, "TD", "25")
    _visit(seed, _appointment(seed), _dose("TD"), actor=seed.doctor_actor)

    money_doctor = replace(seed.doctor_actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[seed.doctor_actor.role] | {Permission.ANALYTICS_MONEY}))
    overview = GetAnalyticsOverview(_uow(seed), FixedClock()).execute(
        money_doctor, AnalyticsQuery(start=TODAY, end=TODAY)
    )

    assert overview.current.income == Decimal("25.00")


def test_the_vaccination_report_shows_the_supplier(clinic):
    seed, agenda = clinic
    _set(seed, "TD", "25")
    _visit(seed, _appointment(seed, agenda), _dose("TD"), _dose("INFLU", VaccineSupply.MINSAL))

    report = GetReport(_uow(seed), FixedClock()).execute(
        _admin(seed), ReportQuery("vaccinations", TODAY, TODAY)
    )

    keys = [c.key for c in report.detail.columns]
    assert [r[keys.index("supply")] for r in report.detail.rows] == ["clinic", "minsal"]
