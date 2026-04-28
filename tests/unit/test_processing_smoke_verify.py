from __future__ import annotations

from event_driven_audio_analytics.processing.modules.publisher import (
    build_audio_features_event,
    build_system_metrics_event,
)
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import build_envelope
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload
from event_driven_audio_analytics.smoke.verify_processing_flow import (
    _assert_processing_metrics,
    _filter_processing_metric_messages,
)


def _processing_feature_message(
    run_id: str,
    *,
    track_id: int = 2,
    segment_idx: int = 0,
    silent_flag: bool = False,
    processing_ms: float = 12.5,
) -> dict[str, object]:
    envelope = build_audio_features_event(
        AudioFeaturesPayload(
            ts="2026-04-04T00:00:10Z",
            run_id=run_id,
            track_id=track_id,
            segment_idx=segment_idx,
            artifact_uri=f"/artifacts/runs/{run_id}/segments/{track_id}/{segment_idx}.wav",
            checksum=f"sha256:{track_id:06d}{segment_idx:06d}",
            rms=-12.5,
            silent_flag=silent_flag,
            mel_bins=128,
            mel_frames=300,
            processing_ms=processing_ms,
        ),
        trace_id=f"run/{run_id}/track/{track_id}",
    ).to_dict()
    return {
        "key": str(track_id),
        "envelope": envelope,
    }


def _processing_metric_message(
    run_id: str,
    *,
    metric_name: str,
    metric_value: float,
    labels_json: dict[str, object],
    unit: str,
    service_name: str = "processing",
    ts: str = "2026-04-04T00:00:11Z",
) -> dict[str, object]:
    payload = SystemMetricsPayload(
        ts=ts,
        run_id=run_id,
        service_name=service_name,
        metric_name=metric_name,
        metric_value=metric_value,
        labels_json=labels_json,
        unit=unit,
    )
    if service_name == "processing":
        envelope = build_system_metrics_event(
            payload,
            trace_id=f"run/{run_id}/service/{service_name}",
        ).to_dict()
    else:
        envelope = build_envelope(
            event_type="system.metrics",
            source_service=service_name,
            payload=payload,
            trace_id=f"run/{run_id}/service/{service_name}",
        ).to_dict()
    return {
        "key": service_name,
        "envelope": envelope,
    }


def test_filter_processing_metric_messages_ignores_other_services() -> None:
    messages = [
        _processing_metric_message(
            "demo-run",
            metric_name="processing_ms",
            metric_value=12.5,
            labels_json={"topic": "audio.features", "status": "ok"},
            unit="ms",
        ),
        _processing_metric_message(
            "demo-run",
            metric_name="tracks_total",
            metric_value=2.0,
            labels_json={"scope": "run_total"},
            unit="count",
            service_name="ingestion",
        ),
    ]

    filtered = _filter_processing_metric_messages(messages)

    assert len(filtered) == 1
    assert filtered[0]["envelope"]["payload"]["service_name"] == "processing"


def test_assert_processing_metrics_allows_zero_segment_runs() -> None:
    assert _assert_processing_metrics([], feature_messages=[]) == (0, 0, 0.0, 0)


def test_assert_processing_metrics_rejects_feature_errors_on_zero_segment_runs() -> None:
    messages = [
        _processing_metric_message(
            "demo-run",
            metric_name="feature_errors",
            metric_value=1.0,
            labels_json={
                "topic": "audio.segment.ready",
                "status": "error",
                "failure_class": "artifact_not_ready",
            },
            unit="count",
        )
    ]

    try:
        _assert_processing_metrics(messages, feature_messages=[])
    except RuntimeError as exc:
        assert "must not emit feature_errors" in str(exc)
    else:
        raise AssertionError("Expected feature_errors to fail zero-segment processing smoke verification.")


def test_assert_processing_metrics_matches_feature_summaries_for_happy_path() -> None:
    feature_messages = [
        _processing_feature_message(
            "demo-run",
            track_id=2,
            segment_idx=0,
            silent_flag=False,
            processing_ms=12.5,
        ),
        _processing_feature_message(
            "demo-run",
            track_id=2,
            segment_idx=1,
            silent_flag=True,
            processing_ms=20.0,
        ),
    ]
    metric_messages = [
        _processing_metric_message(
            "demo-run",
            metric_name="processing_ms",
            metric_value=12.5,
            labels_json={"topic": "audio.features", "status": "ok"},
            unit="ms",
            ts="2026-04-04T00:00:12Z",
        ),
        _processing_metric_message(
            "demo-run",
            metric_name="silent_ratio",
            metric_value=0.0,
            labels_json={"scope": "run_total"},
            unit="ratio",
            ts="2026-04-04T00:00:12Z",
        ),
        _processing_metric_message(
            "demo-run",
            metric_name="processing_ms",
            metric_value=20.0,
            labels_json={"topic": "audio.features", "status": "ok"},
            unit="ms",
            ts="2026-04-04T00:00:13Z",
        ),
        _processing_metric_message(
            "demo-run",
            metric_name="silent_ratio",
            metric_value=0.5,
            labels_json={"scope": "run_total"},
            unit="ratio",
            ts="2026-04-04T00:00:13Z",
        ),
    ]

    assert _assert_processing_metrics(metric_messages, feature_messages=feature_messages) == (
        2,
        2,
        0.5,
        1,
    )
