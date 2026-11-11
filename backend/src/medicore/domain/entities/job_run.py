"""JobRun — one execution of a scheduled operational task (e.g. the nightly demo reset).

Lets the platform console tell whether a task that should run on a schedule actually ran,
and whether it worked. ``detail`` is a short summary or the error type — never data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class JobRun:
    id: UUID
    job: str  # stable name, e.g. "demo_reset"
    started_at: datetime
    finished_at: datetime
    ok: bool
    detail: str = ""
