"""Basic run-level ingestion metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from event_driven_audio_analytics.shared.metric_labels import run_total_metric_labels
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


def _utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp for metrics emission."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class IngestionRunMetrics:
    """Accumulate the minimal Week 3 ingestion metrics for one run."""

    tracks_total: int = 0
    segments_total: int = 0
    validation_failures: int = 0
    artifact_write_ms: float = 0.0

    def record_track(self, *, segment_count: int, validation_failed: bool, artifact_write_ms: float) -> None:
        """Accumulate one processed track into the run-level totals."""

        self.tracks_total += 1
        self.segments_total += segment_count
        if validation_failed:
            self.validation_failures += 1
        self.artifact_write_ms += artifact_write_ms

    def as_payloads(self, *, run_id: str, service_name: str) -> list[SystemMetricsPayload]:
        """Render the aggregated metrics as canonical system.metrics payloads."""

        ts = _utc_now_iso()
        return [
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="tracks_total",
                metric_value=float(self.tracks_total),
                labels_json=run_total_metric_labels(),
                unit="count",
            ),
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="segments_total",
                metric_value=float(self.segments_total),
                labels_json=run_total_metric_labels(),
                unit="count",
            ),
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="validation_failures",
                metric_value=float(self.validation_failures),
                labels_json=run_total_metric_labels(),
                unit="count",
            ),
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="artifact_write_ms",
                metric_value=round(self.artifact_write_ms, 3),
                labels_json=run_total_metric_labels(),
                unit="ms",
            ),
        ]
