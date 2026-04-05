from __future__ import annotations

import pytest

from event_driven_audio_analytics.smoke.verify_ingestion_flow import SmokeExpectation, TrackExpectation
from event_driven_audio_analytics.smoke.verify_writer_flow import (
    WriterDatabaseSnapshot,
    WriterMetricShape,
    WriterSmokeSummary,
    _env_float,
    _assert_writer_snapshot,
    verify_writer_snapshot_with_retries,
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


def test_assert_writer_snapshot_accepts_happy_path() -> None:
    expectation = _smoke_expectation()
    snapshot = WriterDatabaseSnapshot(
        track_metadata_count=2,
        audio_features_count=3,
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
            "rows_upserted": 15,
            "write_ms": 15,
        },
        writer_metric_shapes={
            WriterMetricShape("rows_upserted", "count", "audio.features", "ok", False): 3,
            WriterMetricShape("rows_upserted", "count", "audio.metadata", "ok", False): 2,
            WriterMetricShape("rows_upserted", "count", "system.metrics", "ok", False): 10,
            WriterMetricShape("write_ms", "ms", "audio.features", "ok", False): 3,
            WriterMetricShape("write_ms", "ms", "audio.metadata", "ok", False): 2,
            WriterMetricShape("write_ms", "ms", "system.metrics", "ok", False): 10,
        },
        writer_rows_upserted_values=(1.0,) * 15,
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
    )

    summary = _assert_writer_snapshot(
        snapshot,
        run_id="demo-run",
        expectation=expectation,
        consumer_group="event-driven-audio-analytics-writer",
    )

    assert summary.metadata_count == 2
    assert summary.feature_count == 3
    assert summary.writer_record_count == 15


def test_assert_writer_snapshot_fails_on_wrong_writer_record_count() -> None:
    expectation = _smoke_expectation()
    snapshot = WriterDatabaseSnapshot(
        track_metadata_count=2,
        audio_features_count=3,
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
            "rows_upserted": 14,
            "write_ms": 14,
        },
        writer_metric_shapes={
            WriterMetricShape("rows_upserted", "count", "audio.features", "ok", False): 3,
            WriterMetricShape("rows_upserted", "count", "audio.metadata", "ok", False): 2,
            WriterMetricShape("rows_upserted", "count", "system.metrics", "ok", False): 9,
            WriterMetricShape("write_ms", "ms", "audio.features", "ok", False): 3,
            WriterMetricShape("write_ms", "ms", "audio.metadata", "ok", False): 2,
            WriterMetricShape("write_ms", "ms", "system.metrics", "ok", False): 9,
        },
        writer_rows_upserted_values=(1.0,) * 14,
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
    )

    with pytest.raises(RuntimeError, match="write_ms count drifted"):
        _assert_writer_snapshot(
            snapshot,
            run_id="demo-run",
            expectation=expectation,
            consumer_group="event-driven-audio-analytics-writer",
        )


def test_assert_writer_snapshot_fails_on_writer_metric_contract_drift() -> None:
    expectation = _smoke_expectation()
    snapshot = WriterDatabaseSnapshot(
        track_metadata_count=2,
        audio_features_count=3,
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
            "rows_upserted": 15,
            "write_ms": 15,
        },
        writer_metric_shapes={
            WriterMetricShape("rows_upserted", "count", "audio.features", "ok", False): 3,
            WriterMetricShape("rows_upserted", "count", "audio.metadata", "ok", False): 2,
            WriterMetricShape("rows_upserted", "count", "system.metrics", "ok", False): 10,
            WriterMetricShape("write_ms", "count", "audio.features", "ok", False): 3,
            WriterMetricShape("write_ms", "ms", "audio.metadata", "ok", False): 2,
            WriterMetricShape("write_ms", "ms", "system.metrics", "ok", False): 10,
        },
        writer_rows_upserted_values=(1.0,) * 15,
        checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
    )

    with pytest.raises(RuntimeError, match="writer metric contract drifted"):
        _assert_writer_snapshot(
            snapshot,
            run_id="demo-run",
            expectation=expectation,
            consumer_group="event-driven-audio-analytics-writer",
        )


def test_env_float_rejects_non_positive_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRITER_SMOKE_VERIFY_TIMEOUT_S", "0")

    with pytest.raises(ValueError, match="must be positive"):
        _env_float("WRITER_SMOKE_VERIFY_TIMEOUT_S", 30.0)


def test_verify_writer_snapshot_with_retries_waits_for_eventual_consistency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expectation = _smoke_expectation()
    snapshots = iter([object(), object()])
    monotonic_values = iter([0.0, 0.1, 0.2, 0.3])
    observed_sleeps: list[float] = []
    call_count = {"assertions": 0}

    def fake_query_writer_snapshot(*, run_id: str, consumer_group: str) -> object:
        assert run_id == "demo-run"
        assert consumer_group == "event-driven-audio-analytics-writer"
        return next(snapshots)

    def fake_assert_writer_snapshot(
        snapshot: object,
        *,
        run_id: str,
        expectation: SmokeExpectation,
        consumer_group: str,
    ) -> WriterSmokeSummary:
        call_count["assertions"] += 1
        assert run_id == "demo-run"
        assert consumer_group == "event-driven-audio-analytics-writer"
        assert expectation.track_expectations[2].segment_indices == (0, 1, 2)
        if call_count["assertions"] == 1:
            raise RuntimeError("snapshot not ready yet")
        return WriterSmokeSummary(
            run_id=run_id,
            metadata_count=2,
            feature_count=3,
            ingestion_metric_count=4,
            processing_metric_count=4,
            writer_record_count=15,
            checkpoint_topics=("audio.features", "audio.metadata", "system.metrics"),
        )

    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow._query_writer_snapshot",
        fake_query_writer_snapshot,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow._assert_writer_snapshot",
        fake_assert_writer_snapshot,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow.sleep",
        observed_sleeps.append,
    )

    summary = verify_writer_snapshot_with_retries(
        run_id="demo-run",
        consumer_group="event-driven-audio-analytics-writer",
        expectation=expectation,
        timeout_s=30.0,
        poll_interval_s=1.5,
    )

    assert summary.writer_record_count == 15
    assert observed_sleeps == [1.5]


def test_verify_writer_snapshot_with_retries_raises_last_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expectation = _smoke_expectation()
    monotonic_values = iter([0.0, 0.1, 30.1])

    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow._query_writer_snapshot",
        lambda **_: object(),
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow._assert_writer_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("snapshot never converged")),
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_writer_flow.sleep",
        lambda _: None,
    )

    with pytest.raises(RuntimeError, match="snapshot never converged"):
        verify_writer_snapshot_with_retries(
            run_id="demo-run",
            consumer_group="event-driven-audio-analytics-writer",
            expectation=expectation,
            timeout_s=30.0,
            poll_interval_s=1.0,
        )
