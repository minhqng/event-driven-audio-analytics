from __future__ import annotations

import pytest

from event_driven_audio_analytics.smoke.verify_ingestion_flow import SmokeExpectation, TrackExpectation
from event_driven_audio_analytics.smoke.verify_restart_replay_flow import (
    FeatureRowSnapshot,
    MetadataRowSnapshot,
    RestartReplaySnapshot,
    _assert_baseline_snapshot,
    _assert_replay_snapshot,
    resolve_replay_run_id,
    validate_cleanup_run_id,
)


def _smoke_expectation() -> SmokeExpectation:
    return SmokeExpectation(
        track_expectations={
            2: TrackExpectation(
                track_id=2,
                validation_status="validated",
                segment_indices=(0, 1, 2),
            ),
            666: TrackExpectation(
                track_id=666,
                validation_status="probe_failed",
                segment_indices=(),
            ),
        }
    )


def _metadata_rows() -> tuple[MetadataRowSnapshot, ...]:
    return (
        MetadataRowSnapshot(
            track_id=2,
            artist_id=11,
            genre="Electronic",
            subset="small",
            source_audio_uri="/app/tests/fixtures/audio/smoke_fma_small/000/000002.mp3",
            validation_status="validated",
            duration_s=6.0,
            manifest_uri="/app/artifacts/runs/week8-replay/manifests/segments.parquet",
            checksum="sha256:track-2",
        ),
        MetadataRowSnapshot(
            track_id=666,
            artist_id=22,
            genre="Electronic",
            subset="small",
            source_audio_uri="/app/tests/fixtures/audio/smoke_fma_small/000/000666.mp3",
            validation_status="probe_failed",
            duration_s=6.0,
            manifest_uri=None,
            checksum=None,
        ),
    )


def _feature_rows() -> tuple[FeatureRowSnapshot, ...]:
    return (
        FeatureRowSnapshot(
            track_id=2,
            segment_idx=0,
            artifact_uri="/app/artifacts/runs/week8-replay/segments/2/0.wav",
            checksum="sha256:segment-0",
            manifest_uri="/app/artifacts/runs/week8-replay/manifests/segments.parquet",
            rms=-12.0,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
        ),
        FeatureRowSnapshot(
            track_id=2,
            segment_idx=1,
            artifact_uri="/app/artifacts/runs/week8-replay/segments/2/1.wav",
            checksum="sha256:segment-1",
            manifest_uri="/app/artifacts/runs/week8-replay/manifests/segments.parquet",
            rms=-12.1,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
        ),
        FeatureRowSnapshot(
            track_id=2,
            segment_idx=2,
            artifact_uri="/app/artifacts/runs/week8-replay/segments/2/2.wav",
            checksum="sha256:segment-2",
            manifest_uri="/app/artifacts/runs/week8-replay/manifests/segments.parquet",
            rms=-12.2,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
        ),
    )


def _baseline_snapshot() -> RestartReplaySnapshot:
    return RestartReplaySnapshot(
        run_id="week8-replay",
        metadata_rows=_metadata_rows(),
        feature_rows=_feature_rows(),
        ingestion_metric_counts={
            "artifact_write_ms": 1,
            "segments_total": 1,
            "tracks_total": 1,
            "validation_failures": 1,
        },
        processing_metric_counts={
            "processing_ms": 3,
            "silent_ratio": 1,
        },
        writer_metric_counts={
            "write_ms": 15,
            "rows_upserted": 15,
        },
        checkpoint_offsets={
            "audio.features": 2,
            "audio.metadata": 1,
            "system.metrics": 9,
        },
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
        processing_state_segments=3,
        processing_state_silent_segments=0,
        processing_state_silent_ratio=0.0,
        feature_silent_segments=0,
        persisted_silent_ratio=0.0,
    )


def test_assert_baseline_snapshot_accepts_happy_path() -> None:
    _assert_baseline_snapshot(
        _baseline_snapshot(),
        expectation=_smoke_expectation(),
    )


def test_assert_baseline_snapshot_rejects_processing_state_drift() -> None:
    snapshot = _baseline_snapshot()
    snapshot.processing_state_segments = 2

    with pytest.raises(RuntimeError, match="Processing replay state drifted"):
        _assert_baseline_snapshot(
            snapshot,
            expectation=_smoke_expectation(),
        )


def test_assert_replay_snapshot_accepts_one_rerun_same_run_id() -> None:
    summary = _assert_replay_snapshot(
        RestartReplaySnapshot(
            run_id="week8-replay",
            metadata_rows=_metadata_rows(),
            feature_rows=_feature_rows(),
            ingestion_metric_counts={
                "artifact_write_ms": 1,
                "segments_total": 1,
                "tracks_total": 1,
                "validation_failures": 1,
            },
            processing_metric_counts={
                "processing_ms": 6,
                "silent_ratio": 1,
            },
            writer_metric_counts={
                "write_ms": 30,
                "rows_upserted": 30,
            },
            checkpoint_offsets={
                "audio.features": 5,
                "audio.metadata": 3,
                "system.metrics": 19,
            },
            checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
            processing_state_segments=3,
            processing_state_silent_segments=0,
            processing_state_silent_ratio=0.0,
            feature_silent_segments=0,
            persisted_silent_ratio=0.0,
        ),
        baseline=_baseline_snapshot(),
        expectation=_smoke_expectation(),
    )

    assert summary.processing_ms_count == 6
    assert summary.writer_write_ms_count == 30


def test_assert_replay_snapshot_rejects_feature_row_inflation() -> None:
    current = RestartReplaySnapshot(
        run_id="week8-replay",
        metadata_rows=_metadata_rows(),
        feature_rows=_feature_rows()
        + (
            FeatureRowSnapshot(
                track_id=2,
                segment_idx=3,
                artifact_uri="/app/artifacts/runs/week8-replay/segments/2/3.wav",
                checksum="sha256:segment-3",
                manifest_uri="/app/artifacts/runs/week8-replay/manifests/segments.parquet",
                rms=-12.3,
                silent_flag=False,
                mel_bins=128,
                mel_frames=300,
            ),
        ),
        ingestion_metric_counts={
            "artifact_write_ms": 1,
            "segments_total": 1,
            "tracks_total": 1,
            "validation_failures": 1,
        },
        processing_metric_counts={
            "processing_ms": 6,
            "silent_ratio": 1,
        },
        writer_metric_counts={
            "write_ms": 30,
            "rows_upserted": 30,
        },
        checkpoint_offsets={
            "audio.features": 5,
            "audio.metadata": 3,
            "system.metrics": 19,
        },
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
        processing_state_segments=4,
        processing_state_silent_segments=0,
        processing_state_silent_ratio=0.0,
        feature_silent_segments=0,
        persisted_silent_ratio=0.0,
    )

    with pytest.raises(RuntimeError, match="audio_features rows"):
        _assert_replay_snapshot(
            current,
            baseline=_baseline_snapshot(),
            expectation=_smoke_expectation(),
        )


def test_assert_replay_snapshot_rejects_checkpoint_stall() -> None:
    current = RestartReplaySnapshot(
        run_id="week8-replay",
        metadata_rows=_metadata_rows(),
        feature_rows=_feature_rows(),
        ingestion_metric_counts={
            "artifact_write_ms": 1,
            "segments_total": 1,
            "tracks_total": 1,
            "validation_failures": 1,
        },
        processing_metric_counts={
            "processing_ms": 6,
            "silent_ratio": 1,
        },
        writer_metric_counts={
            "write_ms": 30,
            "rows_upserted": 30,
        },
        checkpoint_offsets={
            "audio.features": 2,
            "audio.metadata": 3,
            "system.metrics": 19,
        },
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
        processing_state_segments=3,
        processing_state_silent_segments=0,
        processing_state_silent_ratio=0.0,
        feature_silent_segments=0,
        persisted_silent_ratio=0.0,
    )

    with pytest.raises(RuntimeError, match="did not advance the writer checkpoint offset"):
        _assert_replay_snapshot(
            current,
            baseline=_baseline_snapshot(),
            expectation=_smoke_expectation(),
        )


@pytest.mark.parametrize(
    "run_id",
    (
        "week8-replay",
        "demo-run",
        "run.with_underscores",
        "run with spaces",
    ),
)
def test_validate_cleanup_run_id_accepts_single_segment_run_ids(run_id: str) -> None:
    assert validate_cleanup_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    (
        "",
        "   ",
        ".",
        "..",
        "../escape",
        "..\\escape",
        "nested/run",
        "nested\\run",
        "/absolute",
        "C:\\absolute",
    ),
)
def test_validate_cleanup_run_id_rejects_escape_candidates(run_id: str) -> None:
    with pytest.raises(ValueError, match="empty or whitespace|artifacts/runs"):
        validate_cleanup_run_id(run_id)


def test_resolve_replay_run_id_accepts_matching_env_and_baseline() -> None:
    assert (
        resolve_replay_run_id(
            configured_run_id="week8-replay",
            baseline_run_id="week8-replay",
        )
        == "week8-replay"
    )


def test_resolve_replay_run_id_rejects_baseline_run_id_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match the active RUN_ID"):
        resolve_replay_run_id(
            configured_run_id="week8-replay",
            baseline_run_id="demo-run",
        )


def test_resolve_replay_run_id_rejects_invalid_baseline_run_id() -> None:
    with pytest.raises(ValueError, match="artifacts/runs"):
        resolve_replay_run_id(
            configured_run_id="week8-replay",
            baseline_run_id="../escape",
        )
