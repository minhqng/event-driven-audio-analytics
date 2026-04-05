"""Internal writer metrics emitted directly to TimescaleDB."""

from __future__ import annotations

from datetime import UTC, datetime

from event_driven_audio_analytics.shared.metric_labels import WriterMetricLabelSet
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp in RFC 3339 form."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_writer_metric_payload(
    *,
    run_id: str,
    topic: str,
    metric_name: str,
    metric_value: float,
    unit: str,
    status: str,
    partition: int,
    offset: int,
    failure_class: str | None = None,
) -> SystemMetricsPayload:
    """Build one writer-owned system_metrics payload for direct DB persistence."""

    return SystemMetricsPayload(
        ts=_utc_now_iso(),
        run_id=run_id,
        service_name="writer",
        metric_name=metric_name,
        metric_value=metric_value,
        labels_json=WriterMetricLabelSet(
            topic=topic,
            status=status,
            partition=partition,
            offset=offset,
            failure_class=failure_class,
        ).to_dict(),
        unit=unit,
    )
