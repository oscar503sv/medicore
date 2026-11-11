"""In-process accumulator of request metrics, drained periodically into the database.

Every worker keeps its own counts per (hour, method, route) — a dict update under a lock
per request — and hands them over in batches (``drain``); the store adds batches up, so
several workers and restarts sum correctly. A crash loses at most one flush interval.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from medicore.domain.repositories._support import RequestStatsRow
from medicore.domain.value_objects.latency_histogram import SIZE, LatencyHistogram

FLUSH_SECONDS = 60
UNMATCHED_ROUTE = "(unmatched)"  # 404s on unknown URLs: one bucket, not one row per URL


@dataclass(slots=True)
class _Counts:
    count: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    buckets: list[int] = field(default_factory=lambda: [0] * SIZE)


class RequestRecorder:
    def __init__(self, flush_every: float = FLUSH_SECONDS) -> None:
        self.flush_every = flush_every
        self._lock = threading.Lock()
        self._counts: dict[tuple[datetime, str, str], _Counts] = {}
        self._last_drain = time.monotonic()

    def record(self, hour: datetime, method: str, route: str, status: int, ms: float) -> None:
        with self._lock:
            c = self._counts.setdefault((hour, method, route), _Counts())
            c.count += 1
            if 400 <= status < 500:
                c.client_errors += 1
            elif status >= 500:
                c.server_errors += 1
            c.total_ms += ms
            c.max_ms = max(c.max_ms, ms)
            c.buckets[LatencyHistogram.bucket(ms)] += 1

    def due(self) -> bool:
        return bool(self._counts) and time.monotonic() - self._last_drain >= self.flush_every

    def drain(self) -> list[RequestStatsRow]:
        """Take everything recorded so far (and start over)."""
        with self._lock:
            counts, self._counts = self._counts, {}
            self._last_drain = time.monotonic()
        return [
            RequestStatsRow(
                hour=hour, method=method, route=route, count=c.count,
                client_errors=c.client_errors, server_errors=c.server_errors,
                total_ms=round(c.total_ms, 3), max_ms=round(c.max_ms, 3),
                buckets=tuple(c.buckets),
            )
            for (hour, method, route), c in counts.items()
        ]
