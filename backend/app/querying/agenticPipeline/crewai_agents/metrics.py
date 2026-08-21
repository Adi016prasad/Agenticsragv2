"""
Metrics calculation utilities for agents, flows, and batch evaluations.
"""
from __future__ import annotations

import math
from typing import Dict, List


class LatencyAggregator:
    """Calculates average and tail latency percentiles (p50, p90, p95, p99)."""

    @staticmethod
    def calculate_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
        """Computes statistical percentiles for a list of latency readings."""
        if not latencies_ms:
            return {"avg": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}

        sorted_latencies = sorted(latencies_ms)
        n = len(sorted_latencies)

        def _percentile(p: float) -> float:
            k = (n - 1) * (p / 100.0)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_latencies[int(k)]
            d0 = sorted_latencies[int(f)] * (c - k)
            d1 = sorted_latencies[int(c)] * (k - f)
            return d0 + d1

        return {
            "count": n,
            "avg": round(sum(sorted_latencies) / n, 2),
            "p50": round(_percentile(50), 2),
            "p90": round(_percentile(90), 2),
            "p95": round(_percentile(95), 2),
            "p99": round(_percentile(99), 2),
        }