from __future__ import annotations

import pytest

from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.smoke.verify_ingestion_flow import (
    _assert_metric_messages,
    _assert_expected_count,
    _filter_messages_for_run,
)


def _smoke_message(
    run_id: str,
    *,
    track_id: int | None = None,
    metric_name: str | None = None,
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

    with pytest.raises(RuntimeError, match="Expected 2 messages on audio.metadata for run_id=demo-run, but observed 3."):
        _assert_expected_count(
            AUDIO_METADATA,
            messages,
            expected_count=2,
            run_id="demo-run",
        )


def test_expected_count_fails_when_current_run_overpublishes_segment_ready() -> None:
    messages = [
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
        _smoke_message("demo-run", track_id=2),
    ]

    with pytest.raises(RuntimeError, match="Expected 3 messages on audio.segment.ready for run_id=demo-run, but observed 4."):
        _assert_expected_count(
            AUDIO_SEGMENT_READY,
            messages,
            expected_count=3,
            run_id="demo-run",
        )


def test_expected_count_fails_when_current_run_overpublishes_system_metrics() -> None:
    messages = [
        _smoke_message("demo-run", metric_name="tracks_total"),
        _smoke_message("demo-run", metric_name="segments_total"),
        _smoke_message("demo-run", metric_name="validation_failures"),
        _smoke_message("demo-run", metric_name="artifact_write_ms"),
        _smoke_message("demo-run", metric_name="artifact_write_ms"),
    ]

    with pytest.raises(RuntimeError, match="Expected 4 messages on system.metrics for run_id=demo-run, but observed 5."):
        _assert_expected_count(
            SYSTEM_METRICS,
            messages,
            expected_count=4,
            run_id="demo-run",
        )


def test_metric_messages_fail_when_service_name_drifts_from_ingestion() -> None:
    messages = [
        _smoke_message("demo-run", metric_name="tracks_total", service_name="processing"),
        _smoke_message("demo-run", metric_name="segments_total"),
        _smoke_message("demo-run", metric_name="validation_failures"),
        _smoke_message("demo-run", metric_name="artifact_write_ms"),
    ]

    with pytest.raises(RuntimeError, match="service_name=ingestion"):
        _assert_metric_messages(messages)


def test_metric_messages_fail_when_scope_drifts_from_run_total() -> None:
    messages = [
        _smoke_message("demo-run", metric_name="tracks_total", labels_json={"scope": "per_track"}),
        _smoke_message("demo-run", metric_name="segments_total"),
        _smoke_message("demo-run", metric_name="validation_failures"),
        _smoke_message("demo-run", metric_name="artifact_write_ms"),
    ]

    with pytest.raises(RuntimeError, match="run_total snapshots"):
        _assert_metric_messages(messages)
