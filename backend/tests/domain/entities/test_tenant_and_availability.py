"""Tests for Tenant invariants and DoctorAvailability structure."""

from __future__ import annotations

from datetime import date, time

import pytest

from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    ExceptionId,
    LocationId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.time_range import TimeRange


def make_tenant(locations=None) -> Tenant:
    tid = TenantId.new()
    locs = locations if locations is not None else [
        Location(id=LocationId.new(), tenant_id=tid, name="Madrid · Atocha")
    ]
    return Tenant(
        id=tid,
        legal_name="Clínica Norte SL",
        tax_id="B12345678",
        slug=Slug("clinica-norte"),
        timezone="Europe/Madrid",
        locations=locs,
    )


class TestTenant:
    def test_requires_at_least_one_location(self):
        with pytest.raises(InvalidValueObject):
            make_tenant(locations=[])

    def test_promotes_first_location_to_primary(self):
        t = make_tenant()
        assert t.primary_location.is_primary

    def test_rejects_multiple_primaries(self):
        tid = TenantId.new()
        with pytest.raises(InvalidValueObject):
            Tenant(
                id=tid,
                legal_name="x",
                tax_id="y",
                slug=Slug("x"),
                timezone="Europe/Madrid",
                locations=[
                    Location(LocationId.new(), tid, "A", is_primary=True),
                    Location(LocationId.new(), tid, "B", is_primary=True),
                ],
            )


class TestAvailability:
    def test_defaults_to_seven_disabled_days(self):
        av = DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=TenantId.new(), doctor_id=UserId.new()
        )
        assert len(av.weekly) == 7
        assert all(not d.enabled for d in av.weekly)

    def test_weekly_day_rejects_overlapping_blocks(self):
        with pytest.raises(InvalidValueObject):
            WeeklyDay(
                day_of_week=0,
                enabled=True,
                blocks=[
                    TimeRange(time(9, 0), time(13, 0)),
                    TimeRange(time(12, 0), time(14, 0)),
                ],
            )

    def test_extra_exception_requires_blocks(self):
        with pytest.raises(InvalidValueObject):
            AvailabilityException(
                id=ExceptionId.new(), date=date(2026, 6, 1), kind=AvailabilityExceptionKind.EXTRA
            )

    def test_cannot_add_duplicate_exception_date(self):
        av = DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=TenantId.new(), doctor_id=UserId.new()
        )
        ex = AvailabilityException(
            id=ExceptionId.new(), date=date(2026, 6, 1), kind=AvailabilityExceptionKind.OFF
        )
        av.add_exception(ex)
        with pytest.raises(DomainError):
            av.add_exception(
                AvailabilityException(
                    id=ExceptionId.new(),
                    date=date(2026, 6, 1),
                    kind=AvailabilityExceptionKind.OFF,
                )
            )

    def test_booking_rules_validate_slot_minutes(self):
        with pytest.raises(InvalidValueObject):
            BookingRules(slot_minutes=37)

    def test_booking_rules_reject_negative_min_advance(self):
        with pytest.raises(InvalidValueObject):
            BookingRules(min_advance_hours=-1)
