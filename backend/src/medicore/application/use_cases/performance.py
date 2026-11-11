"""Platform console · Performance: how fast and how reliably the API answers.

Built from the hourly per-route metrics the request middleware flushes (see
``application.common.request_stats``): volume, 4xx/5xx rates, latency percentiles from the
merged histograms, the slowest routes and the volume per hour. Shown on the Monitoring page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.repositories._support import RequestStatsRow
from medicore.domain.value_objects.latency_histogram import LatencyHistogram

STATS_RETENTION_DAYS = 30
WINDOW_HOURS = 24
TOP_ROUTES = 10
MIN_SAMPLES = 5  # a route needs this many requests before its p95 means anything


@dataclass(frozen=True, slots=True)
class RoutePerformance:
    method: str
    route: str
    count: int
    client_errors: int
    server_errors: int
    avg_ms: float
    p95_ms: float | None
    max_ms: float


@dataclass(frozen=True, slots=True)
class HourVolume:
    hour: datetime
    count: int
    server_errors: int


@dataclass(frozen=True, slots=True)
class PerformanceDTO:
    window_hours: int
    requests: int
    client_errors: int
    server_errors: int
    p50_ms: float | None
    p95_ms: float | None
    slowest: list[RoutePerformance]
    hourly: list[HourVolume]


def hour_of(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _round(ms: float | None) -> float | None:
    return None if ms is None else round(ms, 1)


def summarize(rows: list[RequestStatsRow], now: datetime) -> PerformanceDTO:
    """Fold hourly rows of the last WINDOW_HOURS into totals, per-route figures and a
    zero-filled volume per hour."""
    routes: dict[tuple[str, str], list[RequestStatsRow]] = {}
    hours: dict[datetime, list[int]] = {}
    overall = LatencyHistogram()
    max_ms = 0.0
    for r in rows:
        routes.setdefault((r.method, r.route), []).append(r)
        h = hours.setdefault(r.hour, [0, 0])
        h[0] += r.count
        h[1] += r.server_errors
        overall = overall.merged(LatencyHistogram(r.buckets))
        max_ms = max(max_ms, r.max_ms)

    per_route = []
    for (method, route), rs in routes.items():
        hist = LatencyHistogram()
        for r in rs:
            hist = hist.merged(LatencyHistogram(r.buckets))
        count = sum(r.count for r in rs)
        slowest = max(r.max_ms for r in rs)
        per_route.append(RoutePerformance(
            method=method, route=route, count=count,
            client_errors=sum(r.client_errors for r in rs),
            server_errors=sum(r.server_errors for r in rs),
            avg_ms=round(sum(r.total_ms for r in rs) / count, 1) if count else 0.0,
            p95_ms=_round(hist.percentile(95, slowest)),
            max_ms=round(slowest, 1),
        ))
    ranked = sorted(
        (r for r in per_route if r.count >= MIN_SAMPLES and r.p95_ms is not None),
        key=lambda r: r.p95_ms, reverse=True,
    )

    this_hour = hour_of(now)
    timeline = [this_hour - timedelta(hours=n) for n in range(WINDOW_HOURS - 1, -1, -1)]
    return PerformanceDTO(
        window_hours=WINDOW_HOURS,
        requests=sum(r.count for r in rows),
        client_errors=sum(r.client_errors for r in rows),
        server_errors=sum(r.server_errors for r in rows),
        p50_ms=_round(overall.percentile(50, max_ms or None)),
        p95_ms=_round(overall.percentile(95, max_ms or None)),
        slowest=ranked[:TOP_ROUTES],
        hourly=[HourVolume(h, *hours.get(h, (0, 0))) for h in timeline],
    )


def window_start(now: datetime) -> datetime:
    return hour_of(now) - timedelta(hours=WINDOW_HOURS - 1)


class FlushRequestStats:
    """Store a batch drained from a worker's recorder; drop rows past retention."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, rows: list[RequestStatsRow]) -> None:
        if not rows:
            return
        with self._factory.request_stats() as store:
            store.add(rows)
            store.purge_before(self._clock.now() - timedelta(days=STATS_RETENTION_DAYS))
