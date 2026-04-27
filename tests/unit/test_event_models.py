from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.kafka import deserialize_envelope, serialize_envelope
from event_driven_audio_analytics.shared.metric_labels import error_metric_labels
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import build_envelope, build_idempotency_key
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


class EventModelTests(unittest.TestCase):
    def test_audio_features_envelope_serializes_canonical_v1_fields(self) -> None:
        payload = AudioFeaturesPayload(
            ts="2026-04-02T00:00:10Z",
            run_id="demo-run",
            track_id=2,
            segment_idx=0,
            artifact_uri="/artifacts/runs/demo-run/segments/2/0.wav",
            checksum="sha256:segment-000",
            rms=0.42,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
            processing_ms=12.5,
            manifest_uri="/artifacts/runs/demo-run/manifests/segments.parquet",
        )

        envelope = build_envelope(
            "audio.features",
            "processing",
            payload,
            event_id="evt-features-001",
            produced_at="2026-04-02T00:00:11Z",
        ).to_dict()
        round_trip = deserialize_envelope(serialize_envelope(envelope))

        self.assertEqual(envelope["event_id"], "evt-features-001")
        self.assertEqual(envelope["event_type"], "audio.features")
        self.assertEqual(envelope["event_version"], "v1")
        self.assertEqual(envelope["trace_id"], "run/demo-run/track/2")
        self.assertEqual(envelope["run_id"], "demo-run")
        self.assertEqual(envelope["produced_at"], "2026-04-02T00:00:11Z")
        self.assertEqual(envelope["source_service"], "processing")
        self.assertEqual(envelope["idempotency_key"], "audio.features:v1:demo-run:2:0")
        self.assertEqual(envelope["payload"]["segment_idx"], 0)
        self.assertEqual(envelope["payload"]["mel_bins"], 128)
        self.assertEqual(round_trip, envelope)

    def test_build_envelope_accepts_trace_id_override_when_scoped_to_run(self) -> None:
        payload = AudioFeaturesPayload(
            ts="2026-04-02T00:00:10Z",
            run_id="demo-run",
            track_id=2,
            segment_idx=0,
            artifact_uri="/artifacts/runs/demo-run/segments/2/0.wav",
            checksum="sha256:segment-000",
            rms=0.42,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
            processing_ms=12.5,
        )

        envelope = build_envelope(
            "audio.features",
            "processing",
            payload,
            trace_id="run/demo-run/track/2/custom-hop",
        ).to_dict()

        self.assertEqual(envelope["trace_id"], "run/demo-run/track/2/custom-hop")

    def test_system_metrics_default_labels_are_empty_dict(self) -> None:
        payload = SystemMetricsPayload(
            ts="2026-04-02T00:00:12Z",
            run_id="demo-run",
            service_name="writer",
            metric_name="rows_upserted",
            metric_value=3.0,
        )

        self.assertEqual(payload.labels_json, {})

    def test_system_metrics_envelope_uses_service_trace_and_deterministic_labels_hash(self) -> None:
        payload = SystemMetricsPayload(
            ts="2026-04-02T00:00:12Z",
            run_id="demo-run",
            service_name="processing",
            metric_name="processing_ms",
            metric_value=12.5,
            labels_json={
                "topic": "audio.features",
                "status": "ok",
            },
            unit="ms",
        )
        labels_digest = sha256(
            json.dumps(
                payload.labels_json,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]

        envelope = build_envelope(
            "system.metrics",
            "processing",
            payload,
            event_id="evt-metric-001",
            produced_at="2026-04-02T00:00:13Z",
        ).to_dict()

        self.assertEqual(envelope["trace_id"], "run/demo-run/service/processing")
        self.assertEqual(
            envelope["idempotency_key"],
            (
                "system.metrics:v1:demo-run:processing:processing_ms:"
                f"2026-04-02T00:00:12Z:{labels_digest}"
            ),
        )

    def test_run_total_system_metrics_use_snapshot_identity_not_ts(self) -> None:
        first_payload = SystemMetricsPayload(
            ts="2026-04-03T00:00:00Z",
            run_id="demo-run",
            service_name="ingestion",
            metric_name="tracks_total",
            metric_value=2.0,
            labels_json={"scope": "run_total"},
            unit="count",
        )
        second_payload = SystemMetricsPayload(
            ts="2026-04-03T00:00:30Z",
            run_id="demo-run",
            service_name="ingestion",
            metric_name="tracks_total",
            metric_value=5.0,
            labels_json={"scope": "run_total"},
            unit="count",
        )
        labels_digest = sha256(
            json.dumps(
                first_payload.labels_json,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]

        first_key = build_idempotency_key("system.metrics", first_payload)
        second_key = build_idempotency_key("system.metrics", second_payload)

        self.assertEqual(
            first_key,
            f"system.metrics:v1:demo-run:ingestion:tracks_total:run_total:{labels_digest}",
        )
        self.assertEqual(first_key, second_key)

    def test_processing_record_error_metrics_use_replay_safe_identity(self) -> None:
        labels = error_metric_labels(
            topic="audio.segment.ready", failure_class="artifact_not_ready", partition=0, offset=99
        )
        metric_kwargs = {
            "run_id": "demo-run",
            "service_name": "processing",
            "metric_name": "feature_errors",
            "metric_value": 1.0,
            "labels_json": labels,
            "unit": "count",
        }
        first_payload = SystemMetricsPayload(ts="2026-04-03T00:00:00Z", **metric_kwargs)
        second_payload = SystemMetricsPayload(ts="2026-04-03T00:01:00Z", **metric_kwargs)
        labels_digest = sha256(
            json.dumps(labels, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        first_key = build_idempotency_key("system.metrics", first_payload)

        self.assertEqual(first_key, build_idempotency_key("system.metrics", second_payload))
        self.assertEqual(
            first_key,
            f"system.metrics:v1:demo-run:processing:feature_errors:processing_record:{labels_digest}",
        )


if __name__ == "__main__":
    unittest.main()
