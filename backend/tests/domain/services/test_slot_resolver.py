"""Tests for the slot resolution domain service (critical booking rules)."""

from __future__ import annotations

from datetime import date, datetime, time

from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.services.slot_resolver import (
    BusyInterval,
    SlotStatus,
    is_available,
    resolve_available_slots,
)
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    ExceptionId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.time_range import TimeRange

# A Monday with a 09:00–13:00 morning block.
THE_DAY = date(2026, 6, 1)
assert THE_DAY.weekday() == 0  # sanity: Monday
# "now" = the day before, so min/max advance windows don't interfere by default.
LONG_AGO = datetime(2026, 5, 31, 8, 0)


def make_availability(
    *,
    rules: BookingRules | None = None,
    exceptions: list[AvailabilityException] | None = None,
    monday_enabled: bool = True,
) -> DoctorAvailability:
    weekly = [WeeklyDay(day_of_week=d) for d in range(7)]
    weekly[0] = WeeklyDay(
        day_of_week=0,
        enabled=monday_enabled,
        blocks=[TimeRange(time(9, 0), time(13, 0))],
    )
    return DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=TenantId.new(),
        doctor_id=UserId.new(),
        weekly=weekly,
        exceptions=exceptions or [],
        rules=rules or BookingRules(slot_minutes=30),
    )


def _at(slots, hour, minute=0):
    """Find the slot starting at a given time (slots now span a fixed daily horizon)."""
    target = datetime(2026, 6, 1, hour, minute)
    return next(s for s in slots if s.start == target)


def _free(slots):
    return [s for s in slots if s.status == SlotStatus.FREE]


class TestResolveSlots:
    def test_free_slots_only_within_block_rest_out_of_hours(self):
        slots = resolve_available_slots(make_availability(), THE_DAY, now=LONG_AGO)
        # The grid spans the fixed horizon; only the 09:00–13:00 block is bookable.
        free = _free(slots)
        assert len(free) == 8  # 240 min / 30
        assert free[0].start == datetime(2026, 6, 1, 9, 0)
        assert free[-1].end == datetime(2026, 6, 1, 13, 0)
        # 08:00 is before the block, 13:00 spills past it → out of hours.
        assert _at(slots, 8, 0).status == SlotStatus.OUT_OF_HOURS
        assert _at(slots, 13, 0).status == SlotStatus.OUT_OF_HOURS

    def test_disabled_day_is_all_out_of_hours(self):
        slots = resolve_available_slots(
            make_availability(monday_enabled=False), THE_DAY, now=LONG_AGO
        )
        assert slots  # the grid is still emitted
        assert all(s.status == SlotStatus.OUT_OF_HOURS for s in slots)

    def test_off_exception_blocks_whole_day(self):
        av = make_availability(
            exceptions=[
                AvailabilityException(
                    id=ExceptionId.new(), date=THE_DAY, kind=AvailabilityExceptionKind.OFF
                )
            ]
        )
        slots = resolve_available_slots(av, THE_DAY, now=LONG_AGO)
        assert all(s.status == SlotStatus.OUT_OF_HOURS for s in slots)

    def test_extra_exception_enables_slots_on_disabled_day(self):
        av = make_availability(
            monday_enabled=False,
            exceptions=[
                AvailabilityException(
                    id=ExceptionId.new(),
                    date=THE_DAY,
                    kind=AvailabilityExceptionKind.EXTRA,
                    blocks=[TimeRange(time(16, 0), time(18, 0))],
                )
            ],
        )
        free = _free(resolve_available_slots(av, THE_DAY, now=LONG_AGO))
        assert len(free) == 4  # 120 / 30
        assert free[0].start == datetime(2026, 6, 1, 16, 0)

    def test_busy_interval_marks_slot_taken(self):
        busy = [BusyInterval(datetime(2026, 6, 1, 9, 0), datetime(2026, 6, 1, 9, 30))]
        slots = resolve_available_slots(make_availability(), THE_DAY, busy=busy, now=LONG_AGO)
        assert _at(slots, 9, 0).status == SlotStatus.TAKEN
        assert _at(slots, 9, 30).status == SlotStatus.FREE

    def test_buffer_blocks_adjacent_slot(self):
        av = make_availability(rules=BookingRules(slot_minutes=30, buffer_minutes=15))
        busy = [BusyInterval(datetime(2026, 6, 1, 9, 0), datetime(2026, 6, 1, 9, 30))]
        slots = resolve_available_slots(av, THE_DAY, busy=busy, now=LONG_AGO)
        # 09:30 slot now falls inside the 15-min buffer after the 09:00–09:30 appointment.
        assert _at(slots, 9, 0).status == SlotStatus.TAKEN
        assert _at(slots, 9, 30).status == SlotStatus.TAKEN
        assert _at(slots, 10, 0).status == SlotStatus.FREE

    def test_min_advance_marks_in_hours_slots_blocked_by_rules(self):
        av = make_availability(rules=BookingRules(slot_minutes=30, min_advance_hours=24))
        # "now" is the same morning → in-block slots are within 24h → blocked by rules.
        now = datetime(2026, 6, 1, 8, 0)
        slots = resolve_available_slots(av, THE_DAY, now=now)
        assert _at(slots, 9, 0).status == SlotStatus.BLOCKED_RULES
        # A time outside the block is still out_of_hours, not blocked_rules.
        assert _at(slots, 14, 0).status == SlotStatus.OUT_OF_HOURS

    def test_same_day_disallowed_blocks_in_hours_slots(self):
        av = make_availability(rules=BookingRules(slot_minutes=30, allow_same_day=False))
        now = datetime(2026, 6, 1, 7, 0)
        slots = resolve_available_slots(av, THE_DAY, now=now)
        assert _at(slots, 9, 0).status == SlotStatus.BLOCKED_RULES
        assert not _free(slots)


class TestIsAvailable:
    def test_true_within_block_and_free(self):
        assert is_available(
            make_availability(), datetime(2026, 6, 1, 9, 0), 30, now=LONG_AGO
        )

    def test_false_outside_block(self):
        assert not is_available(
            make_availability(), datetime(2026, 6, 1, 14, 0), 30, now=LONG_AGO
        )

    def test_false_when_not_fully_inside_block(self):
        # 12:45 + 30min = 13:15, spills past 13:00 block end.
        assert not is_available(
            make_availability(), datetime(2026, 6, 1, 12, 45), 30, now=LONG_AGO
        )

    def test_false_when_overlapping_existing(self):
        busy = [BusyInterval(datetime(2026, 6, 1, 9, 0), datetime(2026, 6, 1, 9, 30))]
        assert not is_available(
            make_availability(), datetime(2026, 6, 1, 9, 15), 30, busy=busy, now=LONG_AGO
        )

    def test_false_when_breaks_advance_rule(self):
        av = make_availability(rules=BookingRules(slot_minutes=30, min_advance_hours=48))
        now = datetime(2026, 6, 1, 8, 0)
        assert not is_available(av, datetime(2026, 6, 1, 9, 0), 30, now=now)
