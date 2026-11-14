"""Lifetime rules of a superadmin console session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class PlatformSessionPolicy:
    idle: timedelta = timedelta(minutes=30)
    lifetime: timedelta = timedelta(minutes=480)
    # Throttles last_activity writes so a busy page does not hit the database on every call.
    touch_every: timedelta = timedelta(seconds=60)

    @property
    def lifetime_minutes(self) -> int:
        return int(self.lifetime.total_seconds() // 60)
