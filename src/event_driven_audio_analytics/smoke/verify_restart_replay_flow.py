"""Verify restart and replay behavior for one bounded broker-backed smoke run."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from time import monotonic, sleep

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.processing.modules.metrics import (
    ProcessingRunMetrics,
    processing_metrics_state_path,
)
from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import load_database_settings
from event_driven_audio_analytics.smoke.verify_ingestion_flow import (
    EXPECTED_RUN_TOTAL_METRICS,
    SmokeExpectation,
    _derive_smoke_expectation,
)
from event_driven_audio_analytics.smoke.verify_writer_flow import (
    DEFAULT_VERIFY_POLL_INTERVAL_S,
    DEFAULT_VERIFY_TIMEOUT_S,
    verify_writer_snapshot_with_retries,
)
from event_driven_audio_analytics.writer.config import WriterSettings


EPSILON = 1e-6


def validate_cleanup_run_id(run_id: str) -> str:
    """Validate the host-side replay cleanup run id as one relative path segment."""

    if run_id.strip() == "":
        raise ValueError("RUN_ID must not be empty or whitespace.")
    if run_id in {".", ".."} or any(character in run_id for character in ("/", "\\", ":")):
        raise ValueError(
            "RUN_ID must be a single relative path segment for cleanup under artifacts/runs."
        )
    return run_id


def resolve_replay_run_id(
    *,
    configured_run_id: str,
    baseline_run_id: str | None = None,
) -> str:
    """Return the validated replay run id and reject baseline/env mismatches."""

    resolved_run_id = validate_cleanup_run_id(configured_run_id)
    if baseline_run_id is None:
        return resolved_run_id

    resolved_baseline_run_id = validate_cleanup_run_id(baseline_run_id)
    if resolved_baseline_run_id != resolved_run_id:
        raise ValueError(
            "Baseline run_id does not match the active RUN_ID "
            f"expected={resolved_run_id!r} actual={resolved_baseline_run_id!r}."
        )
    return resolved_run_id


@dataclass(frozen=True, slots=True)
class MetadataRowSnapshot:
    """Stable sink-side metadata fields that should survive rerun/replay unchanged."""

    track_id: int
    artist_id: int
    genre: str
    subset: str
    source_audio_uri: str
    validation_status: str
    duration_s: float
    manifest_uri: str | None
    checksum: str | None


@dataclass(frozen=True, slots=True)
class FeatureRowSnapshot:
    """Stable sink-side feature fields that should survive rerun/replay unchanged."""

    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str | None
    rms: float
    silent_flag: bool
    mel_bins: int
    mel_frames: int


@dataclass(slots=True)
class RestartReplaySnapshot:
    """Observed DB and processing-state view for one run."""

    run_id: str
    metadata_rows: tuple[MetadataRowSnapshot, ...]
    feature_rows: tuple[FeatureRowSnapshot, ...]
    ingestion_metric_counts: dict[str, int]
    processing_metric_counts: dict[str, int]
    writer_metric_counts: dict[str, int]
    checkpoint_offsets: dict[str, int]
    checkpoint_topics: tuple[str, ...]
    processing_state_segments: int
    processing_state_silent_segments: int
    processing_state_silent_ratio: float
    feature_silent_segments: int
    persisted_silent_ratio: float | None

    @property
    def metadata_count(self) -> int:
        return len(self.metadata_rows)

    @property
    def feature_count(self) -> int:
        return len(self.feature_rows)

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "metadata_rows": [asdict(row) for row in self.metadata_rows],
                "feature_rows": [asdict(row) for row in self.feature_rows],
                "ingestion_metric_counts": self.ingestion_metric_counts,
                "processing_metric_counts": self.processing_metric_counts,
                "writer_metric_counts": self.writer_metric_counts,
                "checkpoint_offsets": self.checkpoint_offsets,
                "checkpoint_topics": list(self.checkpoint_topics),
                "processing_state_segments": self.processing_state_segments,
                "processing_state_silent_segments": self.processing_state_silent_segments,
                "processing_state_silent_ratio": self.processing_state_silent_ratio,
                "feature_silent_segments": self.feature_silent_segments,
                "persisted_silent_ratio": self.persisted_silent_ratio,
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw_value: str) -> "RestartReplaySnapshot":
        raw_snapshot = json.loads(raw_value)
        return cls(
            run_id=str(raw_snapshot["run_id"]),
            metadata_rows=tuple(
                MetadataRowSnapshot(**row) for row in raw_snapshot["metadata_rows"]
            ),
            feature_rows=tuple(
                FeatureRowSnapshot(**row) for row in raw_snapshot["feature_rows"]
            ),
            ingestion_metric_counts={
                str(name): int(count)
                for name, count in raw_snapshot["ingestion_metric_counts"].items()
            },
            processing_metric_counts={
                str(name): int(count)
                for name, count in raw_snapshot["processing_metric_counts"].items()
            },
            writer_metric_counts={
                str(name): int(count)
                for name, count in raw_snapshot["writer_metric_counts"].items()
            },
            checkpoint_offsets={
                str(topic): int(offset)
                for topic, offset in raw_snapshot["checkpoint_offsets"].items()
            },
            checkpoint_topics=tuple(str(topic) for topic in raw_snapshot["checkpoint_topics"]),
            processing_state_segments=int(raw_snapshot["processing_state_segments"]),
            processing_state_silent_segments=int(raw_snapshot["processing_state_silent_segments"]),
            processing_state_silent_ratio=float(raw_snapshot["processing_state_silent_ratio"]),
            feature_silent_segments=int(raw_snapshot["feature_silent_segments"]),
            persisted_silent_ratio=(
                None
                if raw_snapshot["persisted_silent_ratio"] is None
                else float(raw_snapshot["persisted_silent_ratio"])
            ),
        )


@dataclass(slots=True)
class RestartReplaySummary:
    """Compact Week 8 summary for restart/replay evidence."""

    run_id: str
    metadata_count: int
    feature_count: int
    feature_silent_segments: int
    processing_ms_count: int
    silent_ratio_count: int
    writer_write_ms_count: int
    writer_rows_upserted_count: int
    baseline_checkpoint_offsets: dict[str, int]
    checkpoint_offsets: dict[str, int]
    processing_state_segments: int
    processing_state_silent_ratio: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def _query_scalar(cursor: object, sql: str, params: tuple[object, ...]) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


def _query_metric_counts(
    cursor: object,
    *,
    run_id: str,
    service_name: str,
) -> dict[str, int]:
    cursor.execute(
        """
        SELECT metric_name, COUNT(*)::int
        FROM system_metrics
        WHERE run_id = %s
          AND service_name = %s
        GROUP BY metric_name
        ORDER BY metric_name;
        """,
        (run_id, service_name),
    )
    return {str(name): int(count) for name, count in cursor.fetchall()}


def _query_metadata_rows(
    cursor: object,
    *,
    run_id: str,
) -> tuple[MetadataRowSnapshot, ...]:
    cursor.execute(
        """
        SELECT
            track_id,
            artist_id,
            genre,
            subset,
            source_audio_uri,
            validation_status,
            duration_s,
            manifest_uri,
            checksum
        FROM track_metadata
        WHERE run_id = %s
        ORDER BY track_id;
        """,
        (run_id,),
    )
    return tuple(
        MetadataRowSnapshot(
            track_id=int(track_id),
            artist_id=int(artist_id),
            genre=str(genre),
            subset=str(subset),
            source_audio_uri=str(source_audio_uri),
            validation_status=str(validation_status),
            duration_s=float(duration_s),
            manifest_uri=str(manifest_uri) if manifest_uri is not None else None,
            checksum=str(checksum) if checksum is not None else None,
        )
        for (
            track_id,
            artist_id,
            genre,
            subset,
            source_audio_uri,
            validation_status,
            duration_s,
            manifest_uri,
            checksum,
        ) in cursor.fetchall()
    )


def _query_feature_rows(
    cursor: object,
    *,
    run_id: str,
) -> tuple[FeatureRowSnapshot, ...]:
    cursor.execute(
        """
        SELECT
            track_id,
            segment_idx,
            artifact_uri,
            checksum,
            manifest_uri,
            rms,
            silent_flag,
            mel_bins,
            mel_frames
        FROM audio_features
        WHERE run_id = %s
        ORDER BY track_id, segment_idx;
        """,
        (run_id,),
    )
    return tuple(
        FeatureRowSnapshot(
            track_id=int(track_id),
            segment_idx=int(segment_idx),
            artifact_uri=str(artifact_uri),
            checksum=str(checksum),
            manifest_uri=str(manifest_uri) if manifest_uri is not None else None,
            rms=float(rms),
            silent_flag=bool(silent_flag),
            mel_bins=int(mel_bins),
            mel_frames=int(mel_frames),
        )
        for (
            track_id,
            segment_idx,
            artifact_uri,
            checksum,
            manifest_uri,
            rms,
            silent_flag,
            mel_bins,
            mel_frames,
        ) in cursor.fetchall()
    )


def _query_checkpoint_offsets(
    cursor: object,
    *,
    run_id: str,
    consumer_group: str,
) -> tuple[dict[str, int], tuple[str, ...]]:
    cursor.execute(
        """
        SELECT topic_name, last_committed_offset
        FROM run_checkpoints
        WHERE run_id = %s
          AND consumer_group = %s
        ORDER BY topic_name;
        """,
        (run_id, consumer_group),
    )
    rows = cursor.fetchall()
    checkpoint_offsets = {str(topic_name): int(offset) for topic_name, offset in rows}
    checkpoint_topics = tuple(str(topic_name) for topic_name, _ in rows)
    return checkpoint_offsets, checkpoint_topics


def _query_latest_processing_silent_ratio(
    cursor: object,
    *,
    run_id: str,
) -> float | None:
    cursor.execute(
        """
        SELECT metric_value
        FROM vw_dashboard_run_total_metrics
        WHERE run_id = %s
          AND service_name = 'processing'
          AND metric_name = 'silent_ratio';
        """,
        (run_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return float(row[0])


def _load_processing_state_snapshot(
    *,
    artifacts_root: Path,
    run_id: str,
) -> tuple[int, int, float]:
    run_metrics = ProcessingRunMetrics.from_state_file(
        processing_metrics_state_path(artifacts_root, run_id),
        run_id=run_id,
    )
    return (
        run_metrics.successful_segments,
        run_metrics.silent_segments,
        run_metrics.silent_ratio,
    )


def _query_restart_replay_snapshot(
    *,
    run_id: str,
    consumer_group: str,
    artifacts_root: Path,
) -> RestartReplaySnapshot:
    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            metadata_rows = _query_metadata_rows(cursor, run_id=run_id)
            feature_rows = _query_feature_rows(cursor, run_id=run_id)
            checkpoint_offsets, checkpoint_topics = _query_checkpoint_offsets(
                cursor,
                run_id=run_id,
                consumer_group=consumer_group,
            )
            persisted_silent_ratio = _query_latest_processing_silent_ratio(
                cursor,
                run_id=run_id,
            )
            ingestion_metric_counts = _query_metric_counts(
                cursor,
                run_id=run_id,
                service_name="ingestion",
            )
            processing_metric_counts = _query_metric_counts(
                cursor,
                run_id=run_id,
                service_name="processing",
            )
            writer_metric_counts = _query_metric_counts(
                cursor,
                run_id=run_id,
                service_name="writer",
            )

    processing_state_segments, processing_state_silent_segments, processing_state_silent_ratio = (
        _load_processing_state_snapshot(
            artifacts_root=artifacts_root,
            run_id=run_id,
        )
    )
    feature_silent_segments = sum(int(row.silent_flag) for row in feature_rows)
    return RestartReplaySnapshot(
        run_id=run_id,
        metadata_rows=metadata_rows,
        feature_rows=feature_rows,
        ingestion_metric_counts=ingestion_metric_counts,
        processing_metric_counts=processing_metric_counts,
        writer_metric_counts=writer_metric_counts,
        checkpoint_offsets=checkpoint_offsets,
        checkpoint_topics=checkpoint_topics,
        processing_state_segments=processing_state_segments,
        processing_state_silent_segments=processing_state_silent_segments,
        processing_state_silent_ratio=processing_state_silent_ratio,
        feature_silent_segments=feature_silent_segments,
        persisted_silent_ratio=persisted_silent_ratio,
    )


def _expected_writer_record_count(expectation: SmokeExpectation) -> int:
    expected_metadata_count = len(expectation.track_expectations)
    expected_feature_count = len(expectation.segment_pairs)
    expected_processing_metric_count = 2 * expected_feature_count
    return (
        expected_metadata_count
        + expected_feature_count
        + len(EXPECTED_RUN_TOTAL_METRICS)
        + expected_processing_metric_count
    )


def _expected_silent_ratio_count(*, expected_feature_count: int) -> int:
    return 1 if expected_feature_count > 0 else 0


def _expected_silent_ratio(snapshot: RestartReplaySnapshot) -> float:
    if snapshot.feature_count == 0:
        return 0.0
    return snapshot.feature_silent_segments / float(snapshot.feature_count)


def _assert_baseline_snapshot(
    snapshot: RestartReplaySnapshot,
    *,
    expectation: SmokeExpectation,
) -> None:
    expected_metadata_count = len(expectation.track_expectations)
    expected_feature_count = len(expectation.segment_pairs)
    expected_writer_record_count = _expected_writer_record_count(expectation)
    expected_checkpoint_topics = {"audio.metadata", "system.metrics"}
    if expected_feature_count > 0:
        expected_checkpoint_topics.add("audio.features")

    if snapshot.metadata_count != expected_metadata_count:
        raise RuntimeError(
            "Baseline replay snapshot metadata count drifted from the selected input count. "
            f"Expected {expected_metadata_count} observed {snapshot.metadata_count}."
        )
    if snapshot.feature_count != expected_feature_count:
        raise RuntimeError(
            "Baseline replay snapshot feature count drifted from the selected segment count. "
            f"Expected {expected_feature_count} observed {snapshot.feature_count}."
        )

    metadata_track_ids = tuple(row.track_id for row in snapshot.metadata_rows)
    if metadata_track_ids != expectation.metadata_track_ids:
        raise RuntimeError(
            "Baseline replay snapshot metadata rows drifted from the selected track ids. "
            f"Observed {metadata_track_ids}."
        )

    feature_pairs = tuple((row.track_id, row.segment_idx) for row in snapshot.feature_rows)
    if feature_pairs != expectation.segment_pairs:
        raise RuntimeError(
            "Baseline replay snapshot feature rows drifted from the selected logical segments. "
            f"Observed {feature_pairs}."
        )
    if any(row.mel_bins != 128 or row.mel_frames != 300 for row in snapshot.feature_rows):
        raise RuntimeError("Baseline replay snapshot feature rows drifted from the locked log-mel shape.")

    if set(snapshot.ingestion_metric_counts) != EXPECTED_RUN_TOTAL_METRICS:
        raise RuntimeError(
            "Baseline replay snapshot ingestion metric set drifted from the run_total contract. "
            f"Observed {sorted(snapshot.ingestion_metric_counts)}."
        )
    if any(count != 1 for count in snapshot.ingestion_metric_counts.values()):
        raise RuntimeError("Baseline replay snapshot ingestion run_total metrics must persist as one row each.")

    if snapshot.processing_metric_counts.get("processing_ms", 0) != expected_feature_count:
        raise RuntimeError(
            "Baseline replay snapshot processing_ms count drifted from the selected segment count. "
            f"Expected {expected_feature_count} observed {snapshot.processing_metric_counts.get('processing_ms', 0)}."
        )
    if (
        snapshot.processing_metric_counts.get("silent_ratio", 0)
        != _expected_silent_ratio_count(expected_feature_count=expected_feature_count)
    ):
        raise RuntimeError(
            "Baseline replay snapshot silent_ratio count drifted from the replay-safe run_total rule. "
            f"Observed {snapshot.processing_metric_counts.get('silent_ratio', 0)}."
        )
    if snapshot.processing_metric_counts.get("feature_errors", 0) != 0:
        raise RuntimeError("Baseline replay snapshot must not persist processing feature_errors.")

    if snapshot.writer_metric_counts.get("write_ms", 0) != expected_writer_record_count:
        raise RuntimeError(
            "Baseline replay snapshot write_ms count drifted from the consumed writer record count. "
            f"Expected {expected_writer_record_count} observed {snapshot.writer_metric_counts.get('write_ms', 0)}."
        )
    if snapshot.writer_metric_counts.get("rows_upserted", 0) != expected_writer_record_count:
        raise RuntimeError(
            "Baseline replay snapshot rows_upserted count drifted from the consumed writer record count. "
            f"Expected {expected_writer_record_count} observed {snapshot.writer_metric_counts.get('rows_upserted', 0)}."
        )
    if snapshot.writer_metric_counts.get("write_failures", 0) != 0:
        raise RuntimeError("Baseline replay snapshot must not persist writer write_failures.")

    if set(snapshot.checkpoint_topics) != expected_checkpoint_topics:
        raise RuntimeError(
            "Baseline replay snapshot checkpoint topics drifted from the exercised writer inputs. "
            f"Expected {sorted(expected_checkpoint_topics)} observed {list(snapshot.checkpoint_topics)}."
        )

    expected_silent_ratio = _expected_silent_ratio(snapshot)
    if snapshot.processing_state_segments != expected_feature_count:
        raise RuntimeError(
            "Processing replay state drifted from the selected segment count. "
            f"Expected {expected_feature_count} observed {snapshot.processing_state_segments}."
        )
    if snapshot.processing_state_silent_segments != snapshot.feature_silent_segments:
        raise RuntimeError(
            "Processing replay state silent-segment count drifted from persisted audio_features. "
            f"Expected {snapshot.feature_silent_segments} observed {snapshot.processing_state_silent_segments}."
        )
    if abs(snapshot.processing_state_silent_ratio - expected_silent_ratio) > EPSILON:
        raise RuntimeError(
            "Processing replay state silent_ratio drifted from persisted audio_features. "
            f"Expected {expected_silent_ratio} observed {snapshot.processing_state_silent_ratio}."
        )
    if (
        snapshot.persisted_silent_ratio is not None
        and abs(snapshot.persisted_silent_ratio - expected_silent_ratio) > EPSILON
    ):
        raise RuntimeError(
            "Persisted silent_ratio drifted from persisted audio_features. "
            f"Expected {expected_silent_ratio} observed {snapshot.persisted_silent_ratio}."
        )


def _assert_replay_snapshot(
    snapshot: RestartReplaySnapshot,
    *,
    baseline: RestartReplaySnapshot,
    expectation: SmokeExpectation,
) -> RestartReplaySummary:
    _assert_baseline_snapshot(baseline, expectation=expectation)

    expected_feature_count = len(expectation.segment_pairs)
    expected_writer_record_count = _expected_writer_record_count(expectation)

    if snapshot.metadata_rows != baseline.metadata_rows:
        raise RuntimeError("Replay rerun drifted track_metadata rows for the same run_id.")
    if snapshot.feature_rows != baseline.feature_rows:
        raise RuntimeError("Replay rerun drifted audio_features rows for the same run_id.")
    if snapshot.ingestion_metric_counts != baseline.ingestion_metric_counts:
        raise RuntimeError("Replay rerun inflated replay-safe ingestion run_total metrics.")

    expected_processing_ms_count = (
        baseline.processing_metric_counts.get("processing_ms", 0) + expected_feature_count
    )
    if snapshot.processing_metric_counts.get("processing_ms", 0) != expected_processing_ms_count:
        raise RuntimeError(
            "Replay rerun processing_ms count did not advance by one bounded rerun. "
            f"Expected {expected_processing_ms_count} observed {snapshot.processing_metric_counts.get('processing_ms', 0)}."
        )
    if (
        snapshot.processing_metric_counts.get("silent_ratio", 0)
        != baseline.processing_metric_counts.get("silent_ratio", 0)
    ):
        raise RuntimeError("Replay rerun inflated replay-safe silent_ratio rows.")
    if snapshot.processing_metric_counts.get("feature_errors", 0) != 0:
        raise RuntimeError("Replay rerun must not persist processing feature_errors.")

    expected_writer_metric_count = (
        baseline.writer_metric_counts.get("write_ms", 0) + expected_writer_record_count
    )
    if snapshot.writer_metric_counts.get("write_ms", 0) != expected_writer_metric_count:
        raise RuntimeError(
            "Replay rerun write_ms count did not advance by one bounded rerun. "
            f"Expected {expected_writer_metric_count} observed {snapshot.writer_metric_counts.get('write_ms', 0)}."
        )
    expected_rows_upserted_count = (
        baseline.writer_metric_counts.get("rows_upserted", 0) + expected_writer_record_count
    )
    if snapshot.writer_metric_counts.get("rows_upserted", 0) != expected_rows_upserted_count:
        raise RuntimeError(
            "Replay rerun rows_upserted count did not advance by one bounded rerun. "
            f"Expected {expected_rows_upserted_count} observed {snapshot.writer_metric_counts.get('rows_upserted', 0)}."
        )
    if snapshot.writer_metric_counts.get("write_failures", 0) != 0:
        raise RuntimeError("Replay rerun must not persist writer write_failures.")

    if snapshot.checkpoint_topics != baseline.checkpoint_topics:
        raise RuntimeError("Replay rerun drifted checkpoint topics for the exercised writer inputs.")

    for topic_name, baseline_offset in baseline.checkpoint_offsets.items():
        current_offset = snapshot.checkpoint_offsets.get(topic_name)
        if current_offset is None:
            raise RuntimeError(
                "Replay rerun is missing a writer checkpoint topic that existed at baseline "
                f"topic={topic_name}."
            )
        if current_offset <= baseline_offset:
            raise RuntimeError(
                "Replay rerun did not advance the writer checkpoint offset "
                f"topic={topic_name} baseline={baseline_offset} current={current_offset}."
            )

    if snapshot.processing_state_segments != baseline.processing_state_segments:
        raise RuntimeError("Replay rerun inflated the restart-recovery processing state segment count.")
    if snapshot.processing_state_silent_segments != baseline.processing_state_silent_segments:
        raise RuntimeError("Replay rerun drifted silent segment recovery state for the same run_id.")
    if abs(snapshot.processing_state_silent_ratio - baseline.processing_state_silent_ratio) > EPSILON:
        raise RuntimeError("Replay rerun drifted the restart-recovery silent_ratio state for the same run_id.")
    if snapshot.feature_silent_segments != baseline.feature_silent_segments:
        raise RuntimeError("Replay rerun drifted persisted silent_flag content for the same run_id.")

    baseline_persisted_silent_ratio = baseline.persisted_silent_ratio or 0.0
    current_persisted_silent_ratio = snapshot.persisted_silent_ratio or 0.0
    if abs(current_persisted_silent_ratio - baseline_persisted_silent_ratio) > EPSILON:
        raise RuntimeError("Replay rerun drifted the persisted silent_ratio snapshot for the same run_id.")

    return RestartReplaySummary(
        run_id=snapshot.run_id,
        metadata_count=snapshot.metadata_count,
        feature_count=snapshot.feature_count,
        feature_silent_segments=snapshot.feature_silent_segments,
        processing_ms_count=snapshot.processing_metric_counts.get("processing_ms", 0),
        silent_ratio_count=snapshot.processing_metric_counts.get("silent_ratio", 0),
        writer_write_ms_count=snapshot.writer_metric_counts.get("write_ms", 0),
        writer_rows_upserted_count=snapshot.writer_metric_counts.get("rows_upserted", 0),
        baseline_checkpoint_offsets=baseline.checkpoint_offsets,
        checkpoint_offsets=snapshot.checkpoint_offsets,
        processing_state_segments=snapshot.processing_state_segments,
        processing_state_silent_ratio=snapshot.processing_state_silent_ratio,
    )


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = float(raw_value)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive when set.")
    return value


def _write_output(path: Path | None, text: str) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


def _capture_baseline_snapshot(
    *,
    run_id: str,
    expectation: SmokeExpectation,
    writer_settings: WriterSettings,
    artifacts_root: Path,
    timeout_s: float,
    poll_interval_s: float,
) -> RestartReplaySnapshot:
    verify_writer_snapshot_with_retries(
        run_id=run_id,
        consumer_group=writer_settings.consumer_group,
        expectation=expectation,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    snapshot = _query_restart_replay_snapshot(
        run_id=run_id,
        consumer_group=writer_settings.consumer_group,
        artifacts_root=artifacts_root,
    )
    _assert_baseline_snapshot(snapshot, expectation=expectation)
    return snapshot


def _verify_replay_snapshot_with_retries(
    *,
    baseline: RestartReplaySnapshot,
    expectation: SmokeExpectation,
    writer_settings: WriterSettings,
    artifacts_root: Path,
    timeout_s: float,
    poll_interval_s: float,
) -> RestartReplaySummary:
    deadline = monotonic() + timeout_s
    last_error: RuntimeError | None = None

    while monotonic() <= deadline:
        snapshot = _query_restart_replay_snapshot(
            run_id=baseline.run_id,
            consumer_group=writer_settings.consumer_group,
            artifacts_root=artifacts_root,
        )
        try:
            return _assert_replay_snapshot(
                snapshot,
                baseline=baseline,
                expectation=expectation,
            )
        except RuntimeError as exc:
            last_error = exc
            if monotonic() >= deadline:
                raise
            sleep(poll_interval_s)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Restart/replay verification timed out without producing a summary.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--output", type=Path)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--baseline", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    ingestion_settings = IngestionSettings.from_env()
    writer_settings = WriterSettings.from_env()
    expectation = _derive_smoke_expectation(ingestion_settings)
    timeout_s = _env_float("RESTART_REPLAY_VERIFY_TIMEOUT_S", DEFAULT_VERIFY_TIMEOUT_S)
    poll_interval_s = _env_float(
        "RESTART_REPLAY_VERIFY_POLL_INTERVAL_S",
        DEFAULT_VERIFY_POLL_INTERVAL_S,
    )

    if args.command == "capture":
        run_id = resolve_replay_run_id(configured_run_id=ingestion_settings.base.run_id)
        snapshot = _capture_baseline_snapshot(
            run_id=run_id,
            expectation=expectation,
            writer_settings=writer_settings,
            artifacts_root=ingestion_settings.base.artifacts_root,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        _write_output(args.output, snapshot.to_json())
        return

    baseline = RestartReplaySnapshot.from_json(args.baseline.read_text(encoding="utf-8"))
    run_id = resolve_replay_run_id(
        configured_run_id=ingestion_settings.base.run_id,
        baseline_run_id=baseline.run_id,
    )
    baseline.run_id = run_id
    summary = _verify_replay_snapshot_with_retries(
        baseline=baseline,
        expectation=expectation,
        writer_settings=writer_settings,
        artifacts_root=ingestion_settings.base.artifacts_root,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    _write_output(args.output, summary.to_json())


if __name__ == "__main__":
    main()
