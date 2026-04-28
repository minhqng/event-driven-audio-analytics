from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_PROBE_FAILED,
    VALIDATION_STATUS_VALIDATED,
    ValidationResult,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord
from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.smoke.verify_ingestion_flow import (
    SmokeExpectation,
    TrackExpectation,
    _assert_expected_count,
    _assert_metadata_messages,
    _assert_metric_messages,
    _derive_smoke_expectation,
    _filter_messages_for_run,
)


def _smoke_message(
    run_id: str,
    *,
    track_id: int | None = None,
    metric_name: str | None = None,
    metric_value: float = 1.0,
    service_name: str = "ingestion",
    labels_json: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    key = "ignored"
    if track_id is not None:
        payload["track_id"] = track_id
        key = str(track_id)
    if metric_name is not None:
        payload["metric_name"] = metric_name
        payload["metric_value"] = metric_value
        payload["service_name"] = service_name
        payload["labels_json"] = labels_json or {"scope": "run_total"}
        key = service_name
    return {
        "key": key,
        "envelope": {
            "run_id": run_id,
            "payload": payload,
        },
    }


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


def test_filter_messages_for_run_ignores_other_runs() -> None:
    messages = [
        _smoke_message("other-run", track_id=999),
        _smoke_message("demo-run", track_id=2),
        _smoke_message("another-run", metric_name="tracks_total"),
    ]

    filtered = _filter_messages_for_run(messages, run_id="demo-run")

    assert filtered == [_smoke_message("demo-run", track_id=2)]


def test_expected_count_fails_when_current_run_overpublishes_metadata() -> None:
    messages = [
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=666),
        _smoke_message("demo-run", track_id=777),
    ]

    with pytest.raises(
        RuntimeError,
        match="Expected 2 messages on audio.metadata for run_id=demo-run, but observed 3.",
    ):
        _assert_expected_count(
            AUDIO_METADATA,
            messages,
            expected_count=2,
            run_id="demo-run",
        )


def test_metadata_messages_fail_when_key_drifts_from_track_id() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        messages = [
            {
                "key": "wrong-key",
                "envelope": {
                    "run_id": "demo-run",
                    "payload": {
                        "track_id": 2,
                        "validation_status": "validated",
                        "manifest_uri": "/artifacts/runs/demo-run/manifests/segments.parquet",
                    },
                },
            },
            {
                "key": "666",
                "envelope": {
                    "run_id": "demo-run",
                    "payload": {
                        "track_id": 666,
                        "validation_status": "probe_failed",
                    },
                },
            },
        ]

        with pytest.raises(RuntimeError, match="keyed by track_id"):
            _assert_metadata_messages(
                messages,
                expectation=_smoke_expectation(),
                artifacts_root=artifacts_root,
                run_id="demo-run",
            )


def test_expected_count_fails_when_current_run_overpublishes_segment_ready() -> None:
    messages = [
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
    ]

    with pytest.raises(
        RuntimeError,
        match="Expected 3 messages on audio.segment.ready for run_id=demo-run, but observed 4.",
    ):
        _assert_expected_count(
            AUDIO_SEGMENT_READY,
            messages,
            expected_count=3,
            run_id="demo-run",
        )


def test_expected_count_fails_when_current_run_overpublishes_system_metrics() -> None:
    messages = [
        _smoke_message("demo-run", metric_name="tracks_total", metric_value=2.0),
        _smoke_message("demo-run", metric_name="segments_total", metric_value=3.0),
        _smoke_message("demo-run", metric_name="validation_failures", metric_value=1.0),
        _smoke_message("demo-run", metric_name="artifact_write_ms", metric_value=42.0),
        _smoke_message("demo-run", metric_name="artifact_write_ms", metric_value=42.0),
    ]

    with pytest.raises(
        RuntimeError,
        match="Expected 4 messages on system.metrics for run_id=demo-run, but observed 5.",
    ):
        _assert_expected_count(
            SYSTEM_METRICS,
            messages,
            expected_count=4,
            run_id="demo-run",
        )


def test_metric_messages_fail_when_service_name_drifts_from_ingestion() -> None:
    messages = [
        _smoke_message("demo-run", metric_name="tracks_total", metric_value=2.0, service_name="processing"),
        _smoke_message("demo-run", metric_name="segments_total", metric_value=3.0),
        _smoke_message("demo-run", metric_name="validation_failures", metric_value=1.0),
        _smoke_message("demo-run", metric_name="artifact_write_ms", metric_value=42.0),
    ]

    with pytest.raises(RuntimeError, match="service_name=ingestion"):
        _assert_metric_messages(messages, expectation=_smoke_expectation())


def test_metric_messages_fail_when_scope_drifts_from_run_total() -> None:
    messages = [
        _smoke_message(
            "demo-run",
            metric_name="tracks_total",
            metric_value=2.0,
            labels_json={"scope": "per_track"},
        ),
        _smoke_message("demo-run", metric_name="segments_total", metric_value=3.0),
        _smoke_message("demo-run", metric_name="validation_failures", metric_value=1.0),
        _smoke_message("demo-run", metric_name="artifact_write_ms", metric_value=42.0),
    ]

    with pytest.raises(RuntimeError, match="run_total snapshots"):
        _assert_metric_messages(messages, expectation=_smoke_expectation())


def test_derive_smoke_expectation_tracks_selected_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        MetadataRecord(
            track_id=2,
            artist_id=1,
            genre_label="Hip-Hop",
            subset="small",
            source_path="000/000002.mp3",
            source_audio_uri="/tmp/000002.mp3",
            declared_duration_s=29.95,
        ),
        MetadataRecord(
            track_id=666,
            artist_id=99,
            genre_label="Experimental",
            subset="small",
            source_path="000/000666.mp3",
            source_audio_uri="/tmp/000666.mp3",
            declared_duration_s=30.6,
        ),
        MetadataRecord(
            track_id=777,
            artist_id=42,
            genre_label="Rock",
            subset="small",
            source_path="000/000777.mp3",
            source_audio_uri="/tmp/000777.mp3",
            declared_duration_s=31.0,
        ),
    ]

    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_ingestion_flow.load_small_subset_metadata",
        lambda *args, **kwargs: records,
    )

    def fake_validate_audio_record(record: MetadataRecord, **kwargs) -> ValidationResult:
        if record.track_id == 2:
            return ValidationResult(
                record=record,
                validation_status=VALIDATION_STATUS_VALIDATED,
                decoded_audio=SimpleNamespace(waveform=object(), sample_rate_hz=32000),
            )
        if record.track_id == 777:
            return ValidationResult(
                record=record,
                validation_status=VALIDATION_STATUS_VALIDATED,
                decoded_audio=SimpleNamespace(waveform=object(), sample_rate_hz=32000),
            )
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_PROBE_FAILED,
        )

    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_ingestion_flow.validate_audio_record",
        fake_validate_audio_record,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.smoke.verify_ingestion_flow.segment_audio",
        lambda **kwargs: (
            [SimpleNamespace(segment_idx=0), SimpleNamespace(segment_idx=1)]
            if kwargs["track_id"] == 2
            else []
        ),
    )

    expectation = _derive_smoke_expectation(
        SimpleNamespace(
            metadata_csv_path="ignored.csv",
            audio_root_path="ignored-root",
            subset="small",
            track_id_allowlist=(),
            max_tracks=3,
            target_sample_rate_hz=32000,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            base=SimpleNamespace(run_id="demo-run"),
        )
    )

    assert expectation.metadata_track_ids == (2, 666, 777)
    assert expectation.validated_track_ids == (2,)
    assert expectation.rejected_track_ids == (666, 777)
    assert expectation.segment_pairs == ((2, 0), (2, 1))
    assert expectation.expected_topic_counts[AUDIO_METADATA] == 3
    assert expectation.expected_topic_counts[AUDIO_SEGMENT_READY] == 2
    assert expectation.expected_topic_counts[SYSTEM_METRICS] == 4
    assert expectation.validation_failures == 2
