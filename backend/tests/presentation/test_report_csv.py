"""CSV cells: translated enums, ages, yes/no, out-of-pocket visits and formula-safe text."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from medicore.application.use_cases.reports import ReportColumn
from medicore.domain.services.immunization import VACCINES
from medicore.presentation.report_csv import VACCINE_NAMES, cell


@pytest.mark.parametrize(("column", "value", "lang", "expected"), [
    (ReportColumn("status", "enum:appointment_status"), "no_show", "es", "No asistió"),
    (ReportColumn("type", "enum:appointment_type"), "follow_up", "en", "Follow-up"),
    (ReportColumn("age", "age"), 8, "es", "8 meses"),
    (ReportColumn("age", "age"), 410, "en", "34 years"),
    (ReportColumn("included", "bool"), True, "es", "Sí"),
    (ReportColumn("charged", "money"), Decimal("12.5"), "es", "12.50"),
    (ReportColumn("date", "date"), date(2026, 5, 4), "es", "2026-05-04"),
    (ReportColumn("time", "time"), time(9, 5), "es", "09:05"),
    (ReportColumn("insurer"), None, "es", "Particular"),
    (ReportColumn("lot"), None, "es", ""),
    (ReportColumn("patient"), "-2+3", "es", "'-2+3"),
    (ReportColumn("patient"), "@SUM(A1)", "es", "'@SUM(A1)"),
    (ReportColumn("vaccine", "vaccine"), "SPR", "en", "MMR"),
    (ReportColumn("dose", "dose"), "booster:1", "es", "Refuerzo 1"),
    (ReportColumn("dose", "dose"), "periodic:10", "en", "Every 10 years"),
    (ReportColumn("dose", "dose"), None, "es", "Fuera del esquema"),
])
def test_cells(column, value, lang, expected):
    assert cell(column, value, lang) == expected


def test_every_vaccine_has_a_name_in_both_languages():
    for lang in ("es", "en"):
        assert set(VACCINES) <= set(VACCINE_NAMES[lang])
