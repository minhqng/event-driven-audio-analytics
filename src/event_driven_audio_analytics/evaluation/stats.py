"""Small deterministic summary helpers for evaluation evidence."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import fmean


def _clean_values(values: Iterable[float]) -> list[float]:
    return sorted(float(value) for value in values)


def percentile(values: Iterable[float], quantile: float) -> float | None:
    """Return a deterministic linearly interpolated percentile."""

    sorted_values = _clean_values(values)
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]

    bounded_quantile = min(max(float(quantile), 0.0), 1.0)
    position = bounded_quantile * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return sorted_values[lower_index] + (
        (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


def summarize_distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    """Summarize one latency or resource distribution."""

    sorted_values = _clean_values(values)
    if not sorted_values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
        }

    return {
        "count": len(sorted_values),
        "min": round(sorted_values[0], 6),
        "p50": round(percentile(sorted_values, 0.50) or 0.0, 6),
        "p95": round(percentile(sorted_values, 0.95) or 0.0, 6),
        "max": round(sorted_values[-1], 6),
        "mean": round(fmean(sorted_values), 6),
    }


def summarize_total(values: Iterable[float]) -> dict[str, float | int | None]:
    """Summarize a run-total metric that is normally emitted once."""

    sorted_values = _clean_values(values)
    total = sum(sorted_values)
    return {
        "count": len(sorted_values),
        "sum": round(total, 6),
        "mean": round(total / len(sorted_values), 6) if sorted_values else None,
    }


def rate_per_minute(count: int | float, duration_s: float) -> float:
    """Return a bounded per-minute rate for one scenario duration."""

    if duration_s <= 0.0:
        return 0.0
    return round(float(count) * 60.0 / duration_s, 6)
