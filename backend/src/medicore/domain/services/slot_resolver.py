"""Slot resolution domain service.

Pure availability logic, kept out of the ``DoctorAvailability`` aggregate so it can combine
the schedule with *external* facts (existing appointments, "now") without the aggregate
needing to know about them.

This is where the critical booking rules live:
  * a slot must fall inside the doctor's availability (weekly blocks + ``extra`` exceptions);
  * an ``off`` exception blocks the whole day;
  * a slot must not overlap an existing appointment;
  * booking-rule windows (min advance, same-day) are honored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.value_objects.time_range import TimeRange

# Fixed grid the slot resolver paints, regardless of the doctor's actual blocks. Candidates
# outside the effective availability are returned as OUT_OF_HOURS (not omitted) so the UI can
# draw the full day and the user sees *why* a time isn't offered. (SPEC PARTE B, paso 2.)
HORIZON_START = time(8, 0)
HORIZON_END = time(19, 0)


class SlotStatus(StrEnum):
    FREE = "free"
    TAKEN = "taken"
    OUT_OF_HOURS = "out_of_hours"  # outside the doctor's effective availability
    BLOCKED_RULES = "blocked_rules"  # inside hours & free, but breaks a booking rule


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


def _overlaps_busy(start: datetime, end: datetime, busy: list[BusyInterval]) -> bool:
    return any(start < b.end and b.start < end for b in busy)


def _violates_rules(start: datetime, availability: DoctorAvailability, now: datetime) -> bool:
    rules = availability.rules
    if start < now:  # the slot has already started; a past time is never bookable
        return True
    if not rules.allow_same_day and start.date() == now.date():
        return True
    return bool(
        rules.min_advance_hours and start < now + timedelta(hours=rules.min_advance_hours)
    )


def _fits_in_block(start: datetime, end: datetime, blocks: list[TimeRange]) -> bool:
    """True if ``[start, end)`` is fully contained in some effective availability block."""
    requested = TimeRange(start.time(), _safe_time(end, start))
    return any(block.contains_range(requested) for block in blocks)


def resolve_available_slots(
    availability: DoctorAvailability,
    on: date,
    desired_duration_minutes: int = 30,
    busy: list[BusyInterval] | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    """Generate the day's candidate slots for an appointment of ``desired_duration_minutes``.

    Candidates are stepped by ``rules.slot_minutes`` across a fixed horizon
    (``HORIZON_START``–``HORIZON_END``), not just inside the doctor's blocks, so the UI can
    paint the full day. Status precedence (SPEC PARTE B):

    * not inside an effective block  → ``OUT_OF_HOURS``
    * overlaps an existing appointment → ``TAKEN``
    * breaks a booking rule (min advance / same-day) → ``BLOCKED_RULES``
    * otherwise → ``FREE``
    """
    busy = _normalize_busy(busy or [])
    now = _naive(now or datetime.now())
    blocks = _blocks_for_date(availability, on)
    duration = timedelta(minutes=desired_duration_minutes)
    step = timedelta(minutes=availability.rules.slot_minutes)

    slots: list[Slot] = []
    cursor = datetime.combine(on, HORIZON_START)
    horizon_end = datetime.combine(on, HORIZON_END)
    while cursor < horizon_end:
        slot_end = cursor + duration
        if not _fits_in_block(cursor, slot_end, blocks):
            status = SlotStatus.OUT_OF_HOURS
        elif _overlaps_busy(cursor, slot_end, busy):
            status = SlotStatus.TAKEN
        elif _violates_rules(cursor, availability, now):
            status = SlotStatus.BLOCKED_RULES
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
    interval, and satisfy the booking rules.
    """
    busy = _normalize_busy(busy or [])
    now = _naive(now or datetime.now())
    start = _naive(start)
    end = start + timedelta(minutes=duration_minutes)

    if not _fits_in_block(start, end, _blocks_for_date(availability, start.date())):
        return False
    if _overlaps_busy(start, end, busy):
        return False
    return not _violates_rules(start, availability, now)


def _safe_time(end: datetime, start: datetime) -> time:
    """End time within the same day; an appointment crossing midnight cannot fit a block."""
    if end.date() != start.date():
        # Force an invalid (non-containable) end so the block check fails cleanly.
        return time(23, 59, 59)
    return end.time()
