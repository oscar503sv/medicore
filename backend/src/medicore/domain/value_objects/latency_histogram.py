"""LatencyHistogram — request durations counted in fixed buckets.

Lets the platform console estimate percentiles (p50, p95) per route and hour without
keeping every request: buckets add up across workers and hours, and a percentile is read by
walking the cumulative counts and interpolating inside the bucket that holds it.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

# Upper bounds (ms) of every bucket but the last, which holds anything slower.
BOUNDS_MS: tuple[int, ...] = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
SIZE = len(BOUNDS_MS) + 1


@dataclass(frozen=True, slots=True)
class LatencyHistogram:
    counts: tuple[int, ...] = (0,) * SIZE

    def __post_init__(self) -> None:
        if len(self.counts) != SIZE:
            raise ValueError(f"a latency histogram has {SIZE} buckets")

    @staticmethod
    def bucket(ms: float) -> int:
        """Index of the bucket a duration falls in (bounds are inclusive)."""
        return bisect_left(BOUNDS_MS, ms)

    @classmethod
    def of(cls, *durations_ms: float) -> LatencyHistogram:
        counts = [0] * SIZE
        for ms in durations_ms:
            counts[cls.bucket(ms)] += 1
        return cls(tuple(counts))

    @property
    def total(self) -> int:
        return sum(self.counts)

    def merged(self, other: LatencyHistogram) -> LatencyHistogram:
        pairs = zip(self.counts, other.counts, strict=True)
        return LatencyHistogram(tuple(a + b for a, b in pairs))

    def percentile(self, p: float, max_ms: float | None = None) -> float | None:
        """Estimated ``p``-th percentile (0–100) in ms; None when empty.

        Linear interpolation inside the bucket; the open-ended last bucket answers with the
        slowest duration seen (``max_ms``) or its lower bound.
        """
        total = self.total
        if total == 0:
            return None
        rank = total * p / 100
        seen = 0
        for i, count in enumerate(self.counts):
            if count and seen + count >= rank:
                low = BOUNDS_MS[i - 1] if i > 0 else 0
                if i == len(BOUNDS_MS):
                    return float(max_ms if max_ms is not None else low)
                high = BOUNDS_MS[i]
                if max_ms is not None:
                    high = min(high, max(max_ms, low))
                return low + (high - low) * (rank - seen) / count
            seen += count
        return float(max_ms or BOUNDS_MS[-1])  # pragma: no cover - rank never exceeds total
