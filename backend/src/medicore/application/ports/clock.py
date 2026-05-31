"""Clock port — abstracts the current time so use cases are deterministic in tests."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant (timezone-aware, UTC)."""
        ...
