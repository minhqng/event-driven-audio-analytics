"""Shared metric-label helpers for stable observability queries."""

from __future__ import annotations

from dataclasses import dataclass


RUN_TOTAL_SCOPE = "run_total"
WRITER_RECORD_SCOPE = "writer_record"
PROCESSING_RECORD_SCOPE = "processing_record"


def run_total_metric_labels() -> dict[str, object]:
    """Return the canonical labels for replay-safe run snapshots."""

    return {"scope": RUN_TOTAL_SCOPE}


def success_metric_labels(*, topic: str) -> dict[str, object]:
    """Return the canonical labels for successful append-only metrics."""

    return {
        "topic": topic,
        "status": "ok",
    }


def error_metric_labels(
    *,
    topic: str,
    failure_class: str,
    partition: int | None = None,
    offset: int | None = None,
) -> dict[str, object]:
    """Return the canonical labels for error-path append-only metrics."""

    labels: dict[str, object] = {
        "topic": topic,
        "status": "error",
        "failure_class": failure_class,
    }
    if partition is not None and offset is not None:
        labels.update(
            {
                "scope": PROCESSING_RECORD_SCOPE,
                "partition": partition,
                "offset": offset,
            }
        )
    return labels


@dataclass(frozen=True, slots=True)
class WriterMetricLabelSet:
    """Stable labels for writer-owned direct-to-DB metrics."""

    topic: str
    status: str
    partition: int
    offset: int
    failure_class: str | None = None

    def to_dict(self) -> dict[str, object]:
        labels: dict[str, object] = {
            "scope": WRITER_RECORD_SCOPE,
            "topic": self.topic,
            "status": self.status,
            "partition": self.partition,
            "offset": self.offset,
        }
        if self.failure_class is not None:
            labels["failure_class"] = self.failure_class
        return labels
