"""TimeRange value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A within-a-day time interval ``[start, end)`` where ``start < end``."""

    start: time
    end: time

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise InvalidValueObject(
                f"TimeRange.start ({self.start}) must be before end ({self.end})"
            )

    def duration_minutes(self) -> int:
        start_min = self.start.hour * 60 + self.start.minute
        end_min = self.end.hour * 60 + self.end.minute
        return end_min - start_min

    def contains(self, t: time) -> bool:
        """True if ``t`` falls within ``[start, end)``."""
        return self.start <= t < self.end

    def overlaps(self, other: TimeRange) -> bool:
        """True if the two ranges share any instant (touching endpoints do not overlap)."""
        return self.start < other.end and other.start < self.end

    def contains_range(self, other: TimeRange) -> bool:
        """True if ``other`` is fully inside this range."""
        return self.start <= other.start and other.end <= self.end

    @staticmethod
    def from_datetimes(start: datetime, end: datetime) -> TimeRange:
        return TimeRange(start.time(), end.time())
