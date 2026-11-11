"""Performance metrics: the in-process recorder, the hourly summary and the flush."""

from __future__ import annotations

from datetime import datetime, timedelta

from medicore.application.common.request_stats import RequestRecorder
from medicore.application.use_cases.performance import (
    MIN_SAMPLES,
    STATS_RETENTION_DAYS,
    WINDOW_HOURS,
    FlushRequestStats,
    summarize,
)
from medicore.domain.repositories._support import RequestStatsRow
from medicore.domain.value_objects.latency_histogram import LatencyHistogram
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 31, 9, 30)
HOUR = datetime(2026, 5, 31, 9, 0)


def _row(route="/api/v1/patients", hour=HOUR, durations=(40,) * 10, client=0, server=0,
         method="GET"):
    return RequestStatsRow(
        hour=hour, method=method, route=route, count=len(durations), client_errors=client,
        server_errors=server, total_ms=float(sum(durations)), max_ms=float(max(durations)),
        buckets=LatencyHistogram.of(*durations).counts,
    )


def test_recorder_counts_per_hour_and_route_and_drains():
    rec = RequestRecorder(flush_every=0)
    assert not rec.due()  # nothing recorded yet
    rec.record(HOUR, "GET", "/api/v1/patients", 200, 30)
    rec.record(HOUR, "GET", "/api/v1/patients", 404, 70)
    rec.record(HOUR, "GET", "/api/v1/patients", 503, 900)
    rec.record(HOUR, "POST", "/api/v1/patients", 201, 120)
    assert rec.due()

    rows = {(r.method, r.route): r for r in rec.drain()}
    get = rows[("GET", "/api/v1/patients")]
    assert (get.count, get.client_errors, get.server_errors) == (3, 1, 1)
    assert get.total_ms == 1000 and get.max_ms == 900
    assert sum(get.buckets) == 3
    assert rows[("POST", "/api/v1/patients")].count == 1
    assert rec.drain() == []


def test_recorder_waits_for_the_flush_interval():
    rec = RequestRecorder(flush_every=3600)
    rec.record(HOUR, "GET", "/x", 200, 1)
    assert not rec.due()


def test_summary_totals_percentiles_and_slowest_routes():
    rows = [
        _row("/api/v1/patients", durations=(40,) * 9 + (300,), client=2),
        _row("/api/v1/patients", hour=HOUR - timedelta(hours=1), durations=(40,) * 10),
        _row("/api/v1/reports", durations=(800,) * MIN_SAMPLES, server=1),
        _row("/api/v1/rare", durations=(4000,) * (MIN_SAMPLES - 1)),  # too few to rank
    ]
    dto = summarize(rows, NOW)

    assert dto.requests == 20 + MIN_SAMPLES + MIN_SAMPLES - 1
    assert (dto.client_errors, dto.server_errors) == (2, 1)
    assert dto.p50_ms is not None and dto.p95_ms > dto.p50_ms
    assert [r.route for r in dto.slowest] == ["/api/v1/reports", "/api/v1/patients"]
    patients = dto.slowest[1]
    assert patients.count == 20 and patients.client_errors == 2
    assert patients.avg_ms == round((40 * 19 + 300) / 20, 1)
    assert patients.max_ms == 300


def test_summary_hourly_volume_is_zero_filled():
    dto = summarize([_row(server=1), _row(hour=HOUR - timedelta(hours=5))], NOW)
    assert len(dto.hourly) == WINDOW_HOURS
    assert dto.hourly[-1].hour == HOUR
    assert (dto.hourly[-1].count, dto.hourly[-1].server_errors) == (10, 1)
    assert dto.hourly[-6].count == 10
    assert sum(h.count for h in dto.hourly) == 20


def test_empty_summary():
    dto = summarize([], NOW)
    assert dto.requests == 0 and dto.p95_ms is None and dto.slowest == []


def test_flush_sums_batches_and_purges_old_hours():
    seed = seed_clinic()
    flush = FlushRequestStats(seed.factory, FixedClock(NOW))
    old = _row(hour=HOUR - timedelta(days=STATS_RETENTION_DAYS + 1))
    flush.execute([old, _row(durations=(20, 30))])
    flush.execute([_row(durations=(5000,))])  # another worker, same hour and route

    [stored] = seed.factory.store.request_stats.values()
    assert stored.count == 3
    assert stored.max_ms == 5000
    assert sum(stored.buckets) == 3
