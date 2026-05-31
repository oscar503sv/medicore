"""DateRange value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive date interval ``[from_date, to_date]`` where ``from_date <= to_date``."""

    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if self.from_date > self.to_date:
            raise InvalidValueObject(
                f"DateRange.from_date ({self.from_date}) must be <= to_date ({self.to_date})"
            )

    def contains(self, d: date) -> bool:
        return self.from_date <= d <= self.to_date

    def days(self) -> int:
        """Number of days in the inclusive range."""
        return (self.to_date - self.from_date).days + 1
