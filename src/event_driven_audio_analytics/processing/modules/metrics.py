"""Minimal processing metrics emitted on the canonical system.metrics topic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


def _utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp for metrics emission."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class ProcessingRunMetrics:
    """Track the processing success ratio needed for the Week 5 runtime metrics."""

    successful_segments: int = 0
    silent_segments: int = 0

    def projected_silent_ratio(self, *, silent_flag: bool) -> float:
        """Return the run-level silent ratio after one prospective success."""

        next_successful_segments = self.successful_segments + 1
        next_silent_segments = self.silent_segments + int(silent_flag)
        return next_silent_segments / float(next_successful_segments)

    def record_success(self, *, silent_flag: bool) -> None:
        """Commit one successful segment into the in-memory counters."""

        self.successful_segments += 1
        self.silent_segments += int(silent_flag)

    def build_success_payloads(
        self,
        *,
        run_id: str,
        service_name: str,
        processing_ms: float,
        silent_flag: bool,
    ) -> tuple[SystemMetricsPayload, SystemMetricsPayload]:
        """Build the canonical per-segment and run-total processing metrics."""

        ts = _utc_now_iso()
        silent_ratio = self.projected_silent_ratio(silent_flag=silent_flag)
        return (
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="processing_ms",
                metric_value=processing_ms,
                labels_json={
                    "topic": "audio.features",
                    "status": "ok",
                },
                unit="ms",
            ),
            SystemMetricsPayload(
                ts=ts,
                run_id=run_id,
                service_name=service_name,
                metric_name="silent_ratio",
                metric_value=silent_ratio,
                labels_json={"scope": "run_total"},
                unit="ratio",
            ),
        )

    def build_feature_error_payload(
        self,
        *,
        run_id: str,
        service_name: str,
        failure_class: str,
    ) -> SystemMetricsPayload:
        """Build the per-failure processing metric."""

        return SystemMetricsPayload(
            ts=_utc_now_iso(),
            run_id=run_id,
            service_name=service_name,
            metric_name="feature_errors",
            metric_value=1.0,
            labels_json={
                "topic": "audio.segment.ready",
                "status": "error",
                "failure_class": failure_class,
            },
            unit="count",
        )
