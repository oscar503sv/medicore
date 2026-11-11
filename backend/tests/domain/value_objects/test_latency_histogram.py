"""LatencyHistogram: bucketing, merging and percentile estimates."""

from __future__ import annotations

import pytest

from medicore.domain.value_objects.latency_histogram import BOUNDS_MS, SIZE, LatencyHistogram


def test_bucket_bounds_are_inclusive():
    assert LatencyHistogram.bucket(0) == 0
    assert LatencyHistogram.bucket(10) == 0
    assert LatencyHistogram.bucket(10.1) == 1
    assert LatencyHistogram.bucket(5000) == len(BOUNDS_MS) - 1
    assert LatencyHistogram.bucket(9000) == SIZE - 1


def test_merge_adds_bucket_by_bucket():
    merged = LatencyHistogram.of(5, 30).merged(LatencyHistogram.of(7, 6000))
    assert merged.total == 4
    assert merged.counts[0] == 2 and merged.counts[2] == 1 and merged.counts[-1] == 1


def test_percentiles_interpolate_inside_the_bucket():
    # 100 requests: 90 in (25, 50], 10 in (250, 500]
    h = LatencyHistogram.of(*([40] * 90 + [300] * 10))
    assert h.percentile(50) == pytest.approx(25 + 25 * 50 / 90)
    assert h.percentile(95) == pytest.approx(250 + 250 * 5 / 10)


def test_percentile_is_capped_by_the_slowest_request_seen():
    h = LatencyHistogram.of(*([300] * 10))
    assert h.percentile(95, max_ms=320) <= 320


def test_open_ended_bucket_answers_with_the_max():
    h = LatencyHistogram.of(8000, 9000)
    assert h.percentile(95, max_ms=9000) == 9000


def test_empty_histogram_has_no_percentile():
    assert LatencyHistogram().percentile(95) is None


def test_wrong_size_is_rejected():
    with pytest.raises(ValueError):
        LatencyHistogram((1, 2))
