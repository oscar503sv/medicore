"""DoctorAvailability aggregate: weekly schedule, exceptions and booking rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    ExceptionId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.time_range import TimeRange

_SLOT_CHOICES = frozenset({15, 20, 30, 45, 60})


@dataclass(slots=True)
class WeeklyDay:
    """Availability for one day of the week. ``day_of_week``: 0=Monday … 6=Sunday."""

    day_of_week: int
    enabled: bool = False
    blocks: list[TimeRange] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0 <= self.day_of_week <= 6:
            raise InvalidValueObject(f"day_of_week must be 0..6, got {self.day_of_week}")
        _assert_no_overlaps(self.blocks)


@dataclass(slots=True)
class AvailabilityException:
    """A date that overrides the weekly schedule.

    ``off``  → the doctor is unavailable that whole day (blocks ignored).
    ``extra`` → an additional shift on top of (or outside) the weekly schedule.
    """

    id: ExceptionId
    date: date
    kind: AvailabilityExceptionKind
    reason: str = ""
    blocks: list[TimeRange] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind == AvailabilityExceptionKind.EXTRA and not self.blocks:
            raise InvalidValueObject("An 'extra' exception must define at least one time block")
        _assert_no_overlaps(self.blocks)


@dataclass(frozen=True, slots=True)
class BookingRules:
    """Constraints applied when booking against a doctor's availability.

    ``slot_minutes`` is also the duration of every appointment booked with this doctor —
    callers never choose a duration.
    """

    slot_minutes: int = 30
    min_advance_hours: int = 0
    allow_same_day: bool = True

    def __post_init__(self) -> None:
        if self.slot_minutes not in _SLOT_CHOICES:
            raise InvalidValueObject(
                f"slot_minutes must be one of {sorted(_SLOT_CHOICES)}, got {self.slot_minutes}"
            )
        if self.min_advance_hours < 0:
            raise InvalidValueObject("min_advance_hours must be non-negative")


@dataclass(slots=True)
class DoctorAvailability:
    """One per doctor per tenant. Owns the schedule, exceptions and rules.

    Slot resolution logic lives in ``domain.services.slot_resolver`` to keep this aggregate
    focused on holding state and its own invariants.
    """

    id: AvailabilityId
    tenant_id: TenantId
    doctor_id: UserId
    weekly: list[WeeklyDay] = field(default_factory=list)
    exceptions: list[AvailabilityException] = field(default_factory=list)
    rules: BookingRules = field(default_factory=BookingRules)

    def __post_init__(self) -> None:
        if not self.weekly:
            self.weekly = [WeeklyDay(day_of_week=d) for d in range(7)]
        seen = {d.day_of_week for d in self.weekly}
        if len(seen) != len(self.weekly):
            raise InvalidValueObject("weekly must contain at most one entry per day_of_week")

    def day(self, day_of_week: int) -> WeeklyDay:
        for d in self.weekly:
            if d.day_of_week == day_of_week:
                return d
        raise DomainError(f"No weekly entry for day_of_week={day_of_week}")

    def exception_on(self, on: date) -> AvailabilityException | None:
        for ex in self.exceptions:
            if ex.date == on:
                return ex
        return None

    def set_day(self, day: WeeklyDay) -> None:
        self.weekly = [day if d.day_of_week == day.day_of_week else d for d in self.weekly]

    def add_exception(self, exception: AvailabilityException) -> None:
        if self.exception_on(exception.date) is not None:
            raise DomainError(f"An exception already exists for {exception.date}")
        self.exceptions.append(exception)

    def remove_exception(self, exception_id: ExceptionId) -> None:
        self.exceptions = [e for e in self.exceptions if e.id != exception_id]

    def update_rules(self, rules: BookingRules) -> None:
        self.rules = rules


def _assert_no_overlaps(blocks: list[TimeRange]) -> None:
    ordered = sorted(blocks, key=lambda b: b.start)
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if earlier.overlaps(later):
            raise InvalidValueObject(f"Overlapping time blocks: {earlier} and {later}")
