from __future__ import annotations

import pytest

from event_driven_audio_analytics.evaluation.stats import (
    percentile,
    rate_per_minute,
    summarize_distribution,
    summarize_total,
)


def test_percentile_uses_deterministic_linear_interpolation() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.50) == pytest.approx(2.5)
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == pytest.approx(3.85)


def test_summarize_distribution_returns_schema_for_empty_and_non_empty_values() -> None:
    empty = summarize_distribution([])
    populated = summarize_distribution([3.0, 1.0, 2.0])

    assert empty == {
        "count": 0,
        "min": None,
        "p50": None,
        "p95": None,
        "max": None,
        "mean": None,
    }
    assert populated["count"] == 3
    assert populated["min"] == 1.0
    assert populated["p50"] == 2.0
    assert populated["p95"] == pytest.approx(2.9)
    assert populated["max"] == 3.0
    assert populated["mean"] == 2.0


def test_summarize_total_and_rate_per_minute_are_bounded() -> None:
    assert summarize_total([2.0, 4.0]) == {"count": 2, "sum": 6.0, "mean": 3.0}
    assert summarize_total([]) == {"count": 0, "sum": 0, "mean": None}
    assert rate_per_minute(30, 60.0) == 30.0
    assert rate_per_minute(30, 0.0) == 0.0
