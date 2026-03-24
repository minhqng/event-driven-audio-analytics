from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import build_envelope
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


class EventModelTests(unittest.TestCase):
    def test_audio_features_envelope_serializes_payload(self) -> None:
        payload = AudioFeaturesPayload(
            ts="2026-03-24T00:00:00Z",
            run_id="demo-run",
            track_id=2,
            segment_idx=0,
            artifact_uri="/app/artifacts/runs/demo-run/segments/2/0.wav",
            checksum="abc123",
            manifest_uri="/app/artifacts/runs/demo-run/manifests/segments.parquet",
            rms=0.42,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
            processing_ms=12.5,
        )

        envelope = build_envelope("audio.features", "processing", payload).to_dict()

        self.assertEqual(envelope["event_type"], "audio.features")
        self.assertEqual(envelope["payload"]["segment_idx"], 0)
        self.assertEqual(envelope["payload"]["mel_bins"], 128)

    def test_system_metrics_default_labels_are_empty_dict(self) -> None:
        payload = SystemMetricsPayload(
            ts="2026-03-24T00:00:00Z",
            run_id="demo-run",
            service_name="writer",
            metric_name="rows_upserted",
            metric_value=3.0,
        )

        self.assertEqual(payload.labels_json, {})


if __name__ == "__main__":
    unittest.main()
