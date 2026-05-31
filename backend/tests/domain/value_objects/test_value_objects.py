"""Tests for domain value objects and their invariants."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.date_range import DateRange
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.time_range import TimeRange
from medicore.domain.value_objects.vitals import Vitals


class TestTimeRange:
    def test_requires_start_before_end(self):
        with pytest.raises(InvalidValueObject):
            TimeRange(time(10, 0), time(9, 0))
        with pytest.raises(InvalidValueObject):
            TimeRange(time(9, 0), time(9, 0))

    def test_duration_minutes(self):
        assert TimeRange(time(9, 0), time(13, 0)).duration_minutes() == 240

    def test_contains_is_half_open(self):
        tr = TimeRange(time(9, 0), time(10, 0))
        assert tr.contains(time(9, 0))
        assert tr.contains(time(9, 59))
        assert not tr.contains(time(10, 0))

    def test_overlaps_excludes_touching_endpoints(self):
        a = TimeRange(time(9, 0), time(10, 0))
        b = TimeRange(time(10, 0), time(11, 0))
        c = TimeRange(time(9, 30), time(10, 30))
        assert not a.overlaps(b)
        assert a.overlaps(c)
        assert c.overlaps(a)

    def test_contains_range(self):
        outer = TimeRange(time(9, 0), time(13, 0))
        assert outer.contains_range(TimeRange(time(10, 0), time(11, 0)))
        assert not outer.contains_range(TimeRange(time(12, 0), time(14, 0)))


class TestDateRange:
    def test_requires_from_before_or_equal_to(self):
        with pytest.raises(InvalidValueObject):
            DateRange(date(2026, 5, 2), date(2026, 5, 1))

    def test_days_inclusive(self):
        assert DateRange(date(2026, 5, 1), date(2026, 5, 1)).days() == 1
        assert DateRange(date(2026, 5, 1), date(2026, 5, 3)).days() == 3


class TestBloodType:
    def test_normalizes_and_validates(self):
        assert BloodType(" o+ ").value == "O+"
        with pytest.raises(InvalidValueObject):
            BloodType("XY")


class TestIcdCode:
    @pytest.mark.parametrize("code", ["I10", "E11.9", "S82.101A", "e11.9"])
    def test_accepts_valid(self, code):
        assert IcdCode(code, "label").code == code.upper()

    @pytest.mark.parametrize("code", ["10", "II0", "I1", "U10"])
    def test_rejects_invalid(self, code):
        with pytest.raises(InvalidValueObject):
            IcdCode(code, "label")


class TestSlug:
    def test_accepts_valid(self):
        assert str(Slug("clinica-norte")) == "clinica-norte"

    @pytest.mark.parametrize("value", ["Clinica", "clinica_norte", "-bad", "bad-", "esp acio"])
    def test_rejects_invalid(self, value):
        with pytest.raises(InvalidValueObject):
            Slug(value)


class TestVitals:
    def test_empty_is_valid(self):
        assert Vitals().is_empty()

    def test_bmi(self):
        v = Vitals(weight=Decimal("70"), height=Decimal("175"))
        assert v.bmi() == Decimal("22.9")

    def test_bmi_none_without_measurements(self):
        assert Vitals(weight=Decimal("70")).bmi() is None

    def test_rejects_bad_blood_pressure(self):
        with pytest.raises(InvalidValueObject):
            Vitals(blood_pressure="120-80")

    def test_rejects_out_of_range_spo2(self):
        with pytest.raises(InvalidValueObject):
            Vitals(spo2=120)


class TestMoney:
    def test_add_same_currency(self):
        assert (Money(Decimal("10"), "eur") + Money(Decimal("5"), "EUR")).amount == Decimal("15")

    def test_rejects_mixed_currency(self):
        with pytest.raises(InvalidValueObject):
            Money(Decimal("10"), "EUR") + Money(Decimal("5"), "USD")


class TestSoapNote:
    def test_completion_counts(self):
        assert SoapNote().filled_sections() == 0
        assert SoapNote(subjective="x", plan="y").filled_sections() == 2
        assert SoapNote("a", "b", "c", "d").is_complete()
