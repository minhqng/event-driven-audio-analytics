"""Minimal processing metrics emitted on the canonical system.metrics topic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from os import replace
from pathlib import Path

from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload
from event_driven_audio_analytics.shared.storage import run_root


def _utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp for metrics emission."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ProcessingMetricsStateError(RuntimeError):
    """Raised when the persisted processing metrics state cannot be used safely."""


def processing_metrics_state_path(artifacts_root: Path, run_id: str) -> Path:
    """Return the run-scoped processing metrics state file path."""

    return run_root(artifacts_root, run_id) / "state" / "processing_metrics.json"


@dataclass(slots=True)
class ProcessingRunMetrics:
    """Track the processing success ratio needed for the Week 5 runtime metrics."""

    processed_segments: dict[tuple[int, int], bool] = field(default_factory=dict, repr=False)

    @property
    def successful_segments(self) -> int:
        """Return the count of unique successfully published logical segments."""

        return len(self.processed_segments)

    @property
    def silent_segments(self) -> int:
        """Return the count of unique successful silent logical segments."""

        return sum(int(silent_flag) for silent_flag in self.processed_segments.values())

    @property
    def silent_ratio(self) -> float:
        """Return the current replay-stable silent ratio for this run."""

        if self.successful_segments == 0:
            return 0.0
        return self.silent_segments / float(self.successful_segments)

    def _segment_key(self, *, track_id: int, segment_idx: int) -> tuple[int, int]:
        """Return the stable logical key for one processed segment."""

        return (track_id, segment_idx)

    def with_recorded_success(
        self,
        *,
        track_id: int,
        segment_idx: int,
        silent_flag: bool,
    ) -> "ProcessingRunMetrics":
        """Return the replay-stable run metrics after one logical success."""

        segment_key = self._segment_key(track_id=track_id, segment_idx=segment_idx)
        existing_silent_flag = self.processed_segments.get(segment_key)
        if existing_silent_flag is not None:
            if existing_silent_flag != bool(silent_flag):
                raise ProcessingMetricsStateError(
                    "Processing run metrics state drifted for the logical segment "
                    f"track_id={track_id} segment_idx={segment_idx} "
                    f"expected_silent_flag={existing_silent_flag} actual={bool(silent_flag)}."
                )
            return self

        next_processed_segments = dict(self.processed_segments)
        next_processed_segments[segment_key] = bool(silent_flag)
        return ProcessingRunMetrics(processed_segments=next_processed_segments)

    def build_success_payloads(
        self,
        *,
        run_id: str,
        service_name: str,
        processing_ms: float,
    ) -> tuple[SystemMetricsPayload, SystemMetricsPayload]:
        """Build the canonical per-segment and run-total processing metrics."""

        ts = _utc_now_iso()
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
                metric_value=self.silent_ratio,
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

    def to_state_dict(self, *, run_id: str) -> dict[str, object]:
        """Render the persisted run metrics state as stable JSON data."""

        segments = [
            {
                "track_id": track_id,
                "segment_idx": segment_idx,
                "silent_flag": silent_flag,
            }
            for (track_id, segment_idx), silent_flag in sorted(self.processed_segments.items())
        ]
        return {
            "run_id": run_id,
            "segments": segments,
        }

    def persist(self, *, state_path: Path, run_id: str) -> None:
        """Persist the replay-stable run metrics state for restart recovery."""

        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
            temp_path.write_text(
                json.dumps(self.to_state_dict(run_id=run_id), separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            replace(temp_path, state_path)
        except OSError as exc:
            raise ProcessingMetricsStateError(
                f"Processing metrics state is not writable: {state_path.as_posix()} ({exc})"
            ) from exc

    @classmethod
    def from_state_file(cls, state_path: Path, *, run_id: str) -> "ProcessingRunMetrics":
        """Load the persisted run metrics state if the run has previous progress."""

        if not state_path.exists():
            return cls()
        if not state_path.is_file():
            raise ProcessingMetricsStateError(
                f"Processing metrics state path is not a file: {state_path.as_posix()}"
            )

        try:
            raw_state = json.loads(state_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ProcessingMetricsStateError(
                f"Processing metrics state is not readable: {state_path.as_posix()} ({exc})"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProcessingMetricsStateError(
                f"Processing metrics state is not valid JSON: {state_path.as_posix()} ({exc})"
            ) from exc

        if not isinstance(raw_state, dict):
            raise ProcessingMetricsStateError(
                "Processing metrics state must decode to an object "
                f"path={state_path.as_posix()}."
            )

        persisted_run_id = raw_state.get("run_id")
        if persisted_run_id != run_id:
            raise ProcessingMetricsStateError(
                "Processing metrics state run_id does not match the active run "
                f"expected={run_id} actual={persisted_run_id!r} path={state_path.as_posix()}."
            )

        raw_segments = raw_state.get("segments", [])
        if not isinstance(raw_segments, list):
            raise ProcessingMetricsStateError(
                "Processing metrics state segments must be a list "
                f"path={state_path.as_posix()}."
            )

        processed_segments: dict[tuple[int, int], bool] = {}
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                raise ProcessingMetricsStateError(
                    "Processing metrics state segment rows must be objects "
                    f"path={state_path.as_posix()}."
                )
            track_id = raw_segment.get("track_id")
            segment_idx = raw_segment.get("segment_idx")
            silent_flag = raw_segment.get("silent_flag")
            if (
                not isinstance(track_id, int)
                or isinstance(track_id, bool)
                or not isinstance(segment_idx, int)
                or isinstance(segment_idx, bool)
                or not isinstance(silent_flag, bool)
            ):
                raise ProcessingMetricsStateError(
                    "Processing metrics state segment rows must contain integer track_id, "
                    "integer segment_idx, and boolean silent_flag "
                    f"path={state_path.as_posix()}."
                )
            processed_segments[(track_id, segment_idx)] = silent_flag

        return cls(processed_segments=processed_segments)
