"""Slot resolution domain service.

Pure availability logic, kept out of the ``DoctorAvailability`` aggregate so it can combine
the schedule with *external* facts (existing appointments, "now") without the aggregate
needing to know about them.

This is where the critical booking rules live:
  * a slot must fall inside the doctor's availability (weekly blocks + ``extra`` exceptions);
  * an ``off`` exception blocks the whole day;
  * a slot must not overlap an existing appointment (respecting the configured buffer);
  * booking-rule windows (min/max advance, same-day) are honored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.value_objects.time_range import TimeRange


class SlotStatus(StrEnum):
    FREE = "free"
    TAKEN = "taken"
    OUT_OF_HOURS = "out_of_hours"


@dataclass(frozen=True, slots=True)
class Slot:
    start: datetime
    end: datetime
    status: SlotStatus


@dataclass(frozen=True, slots=True)
class BusyInterval:
    """An occupied interval (e.g. an existing appointment), in the same clock as the schedule."""

    start: datetime
    end: datetime


def _naive(dt: datetime) -> datetime:
    """Drop tzinfo so naive (request/slot) and aware (clock/DB ``timestamptz``) datetimes
    can be compared. Scheduling operates in a single wall-clock reference."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _normalize_busy(busy: list[BusyInterval]) -> list[BusyInterval]:
    return [BusyInterval(_naive(b.start), _naive(b.end)) for b in busy]


def _blocks_for_date(availability: DoctorAvailability, on: date) -> list[TimeRange]:
    """The effective availability blocks for ``on``, applying weekly schedule + exceptions."""
    exception = availability.exception_on(on)
    if exception is not None and exception.kind == AvailabilityExceptionKind.OFF:
        return []  # whole day blocked

    blocks: list[TimeRange] = []
    weekly = availability.day(on.weekday())  # Monday=0, matches WeeklyDay convention
    if weekly.enabled:
        blocks.extend(weekly.blocks)
    if exception is not None and exception.kind == AvailabilityExceptionKind.EXTRA:
        blocks.extend(exception.blocks)
    return sorted(blocks, key=lambda b: b.start)


def _overlaps_busy(
    start: datetime, end: datetime, busy: list[BusyInterval], buffer_minutes: int
) -> bool:
    buffer = timedelta(minutes=buffer_minutes)
    return any(start < b.end + buffer and b.start - buffer < end for b in busy)


def _violates_rules(start: datetime, availability: DoctorAvailability, now: datetime) -> bool:
    rules = availability.rules
    if not rules.allow_same_day and start.date() == now.date():
        return True
    if rules.min_advance_hours and start < now + timedelta(hours=rules.min_advance_hours):
        return True
    max_advance = now.date() + timedelta(days=rules.max_advance_days)
    return bool(rules.max_advance_days and start.date() > max_advance)


def resolve_available_slots(
    availability: DoctorAvailability,
    on: date,
    busy: list[BusyInterval] | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    """Generate the bookable slots for ``on`` with their status.

    Slots are stepped by ``rules.slot_minutes`` within each availability block. A candidate
    that overlaps an existing appointment is ``TAKEN``; one that breaks a booking-rule window
    is ``OUT_OF_HOURS``; otherwise ``FREE``.
    """
    busy = _normalize_busy(busy or [])
    now = _naive(now or datetime.now())
    slot_minutes = availability.rules.slot_minutes
    step = timedelta(minutes=slot_minutes)

    slots: list[Slot] = []
    for block in _blocks_for_date(availability, on):
        cursor = datetime.combine(on, block.start)
        block_end = datetime.combine(on, block.end)
        while cursor + step <= block_end:
            slot_end = cursor + step
            if _overlaps_busy(cursor, slot_end, busy, availability.rules.buffer_minutes):
                status = SlotStatus.TAKEN
            elif _violates_rules(cursor, availability, now):
                status = SlotStatus.OUT_OF_HOURS
            else:
                status = SlotStatus.FREE
            slots.append(Slot(start=cursor, end=slot_end, status=status))
            cursor += step
    return slots


def is_available(
    availability: DoctorAvailability,
    start: datetime,
    duration_minutes: int,
    busy: list[BusyInterval] | None = None,
    now: datetime | None = None,
) -> bool:
    """True if an appointment ``[start, start+duration)`` can be booked.

    Requires the interval to fit entirely within an availability block, not overlap any busy
    interval (respecting buffer), and satisfy the booking rules.
    """
    busy = _normalize_busy(busy or [])
    now = _naive(now or datetime.now())
    start = _naive(start)
    end = start + timedelta(minutes=duration_minutes)

    requested = TimeRange(start.time(), _safe_time(end, start))
    inside_block = any(
        block.contains_range(requested) for block in _blocks_for_date(availability, start.date())
    )
    if not inside_block:
        return False
    if _overlaps_busy(start, end, busy, availability.rules.buffer_minutes):
        return False
    return not _violates_rules(start, availability, now)


def _safe_time(end: datetime, start: datetime) -> time:
    """End time within the same day; an appointment crossing midnight cannot fit a block."""
    if end.date() != start.date():
        # Force an invalid (non-containable) end so the block check fails cleanly.
        return time(23, 59, 59)
    return end.time()
