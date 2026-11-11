"""RuntimeInfo port — facts about the running API process (version, deploy, uptime)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RuntimeFacts:
    version: str
    commit: str | None  # deployed git commit, when the platform provides it
    environment: str
    python: str
    started_at: datetime  # when this process started (per worker)


class RuntimeInfo(Protocol):
    def facts(self) -> RuntimeFacts: ...
