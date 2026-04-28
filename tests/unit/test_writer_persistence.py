from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload
from event_driven_audio_analytics.writer.modules.metrics import build_writer_metric_payload
from event_driven_audio_analytics.writer.modules.persistence import (
    WriterPayloadValidationError,
    coerce_payload_model,
)
from event_driven_audio_analytics.writer.modules.upsert_features import (
    AudioFeaturesNaturalKeyError,
    persist_audio_features,
)
from event_driven_audio_analytics.writer.modules.upsert_metadata import (
    persist_track_metadata,
)
from event_driven_audio_analytics.writer.modules.write_metrics import (
    persist_system_metrics,
)


class FakeCursor:
    def __init__(self, fetch_results: list[list[tuple[object, ...]]] | None = None) -> None:
        self.fetch_results = list(fetch_results or [])
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))
        self.rowcount = 1

    def fetchall(self) -> list[tuple[object, ...]]:
        if not self.fetch_results:
            return []
        return self.fetch_results.pop(0)


class WriterPersistenceTests(unittest.TestCase):
    def build_features_payload(self) -> AudioFeaturesPayload:
        return AudioFeaturesPayload(
            ts="2026-03-24T00:00:10Z",
            run_id="demo-run",
            track_id=2,
            segment_idx=0,
            artifact_uri="/artifacts/runs/demo-run/segments/2/0.wav",
            checksum="abc123",
            manifest_uri="/artifacts/runs/demo-run/manifests/segments.parquet",
            rms=0.42,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
            processing_ms=12.5,
        )

    def build_metadata_payload(self) -> AudioMetadataPayload:
        return AudioMetadataPayload(
            run_id="demo-run",
            track_id=2,
            artist_id=1,
            genre="Hip-Hop",
            source_audio_uri="data/raw/fma_small/000/000002.mp3",
            validation_status="validated",
            duration_s=29.95,
            subset="small",
            manifest_uri="/artifacts/runs/demo-run/manifests/segments.parquet",
            checksum="sha256:track-000002",
        )

    def build_system_metrics_payload(self) -> SystemMetricsPayload:
        return SystemMetricsPayload(
            ts="2026-04-02T00:00:12Z",
            run_id="demo-run",
            service_name="processing",
            metric_name="processing_ms",
            metric_value=12.5,
            labels_json={"topic": "audio.features"},
            unit="ms",
        )

    def build_run_total_metrics_payload(self) -> SystemMetricsPayload:
        return SystemMetricsPayload(
            ts="2026-04-02T00:00:12Z",
            run_id="demo-run",
            service_name="ingestion",
            metric_name="tracks_total",
            metric_value=2.0,
            labels_json={"scope": "run_total"},
            unit="count",
        )

    def build_processing_record_error_payload(self) -> SystemMetricsPayload:
        return SystemMetricsPayload(
            ts="2026-04-02T00:00:12Z",
            run_id="demo-run",
            service_name="processing",
            metric_name="feature_errors",
            metric_value=1.0,
            labels_json={
                "scope": "processing_record",
                "topic": "audio.segment.ready",
                "status": "error",
                "failure_class": "artifact_not_ready",
                "partition": 0,
                "offset": 99,
            },
            unit="count",
        )

    def test_audio_features_inserts_when_natural_key_is_missing(self) -> None:
        cursor = FakeCursor(fetch_results=[[]])

        rows_written = persist_audio_features(cursor, self.build_features_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 3)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("UPDATE audio_features", cursor.executed[1][0])
        self.assertIn("INSERT INTO audio_features", cursor.executed[2][0])

    def test_audio_features_updates_when_natural_key_exists(self) -> None:
        cursor = FakeCursor(fetch_results=[[(1,)]])

        rows_written = persist_audio_features(cursor, self.build_features_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 2)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("UPDATE audio_features", cursor.executed[1][0])

    def test_audio_features_fails_when_natural_key_matches_multiple_rows(self) -> None:
        cursor = FakeCursor(fetch_results=[[(1,), (1,)]])

        with self.assertRaises(AudioFeaturesNaturalKeyError):
            persist_audio_features(cursor, self.build_features_payload())

    def test_audio_features_allows_missing_manifest_uri(self) -> None:
        cursor = FakeCursor(fetch_results=[[]])
        payload = self.build_features_payload()
        payload.manifest_uri = None

        rows_written = persist_audio_features(cursor, payload)

        self.assertEqual(rows_written, 1)
        self.assertIsNone(cursor.executed[2][1]["manifest_uri"])

    def test_coerce_payload_model_rejects_payload_schema_drift(self) -> None:
        with self.assertRaises(WriterPayloadValidationError):
            coerce_payload_model(
                "audio.features",
                {
                    "run_id": "demo-run",
                    "track_id": 2,
                    "segment_idx": 0,
                },
            )

    def test_coerce_payload_model_rejects_non_finite_feature_numbers(self) -> None:
        payload = asdict(self.build_features_payload())
        payload["rms"] = math.nan

        with self.assertRaises(WriterPayloadValidationError):
            coerce_payload_model("audio.features", payload)

    def test_coerce_payload_model_rejects_non_finite_metric_labels(self) -> None:
        payload = asdict(self.build_system_metrics_payload())
        payload["labels_json"]["bad_value"] = math.inf

        with self.assertRaises(WriterPayloadValidationError):
            coerce_payload_model("system.metrics", payload)

    def test_track_metadata_persists_duration_s(self) -> None:
        cursor = FakeCursor()

        rows_written = persist_track_metadata(cursor, self.build_metadata_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 1)
        self.assertIn("duration_s", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1]["duration_s"], 29.95)

    def test_system_metrics_persists_unit(self) -> None:
        cursor = FakeCursor()

        rows_written = persist_system_metrics(cursor, self.build_system_metrics_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 1)
        self.assertIn("unit", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1]["unit"], "ms")

    def test_run_total_system_metrics_rewrites_existing_logical_row(self) -> None:
        cursor = FakeCursor(fetch_results=[[(16432, "(0,7)")]])

        rows_written = persist_system_metrics(cursor, self.build_run_total_metrics_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 4)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("SELECT", cursor.executed[1][0])
        self.assertIn("tableoid::oid", cursor.executed[1][0])
        self.assertIn("ctid::text", cursor.executed[1][0])
        self.assertIn("DELETE FROM system_metrics", cursor.executed[2][0])
        self.assertIn("tableoid = %(survivor_tableoid)s::oid", cursor.executed[2][0])
        self.assertIn("ctid = %(survivor_ctid)s::tid", cursor.executed[2][0])
        self.assertEqual(cursor.executed[2][1]["survivor_tableoid"], 16432)
        self.assertEqual(cursor.executed[2][1]["survivor_ctid"], "(0,7)")
        self.assertIn("INSERT INTO system_metrics", cursor.executed[3][0])

    def test_run_total_system_metrics_inserts_when_logical_row_is_missing(self) -> None:
        cursor = FakeCursor(fetch_results=[[]])

        rows_written = persist_system_metrics(cursor, self.build_run_total_metrics_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 3)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("tableoid::oid", cursor.executed[1][0])
        self.assertIn("ctid::text", cursor.executed[1][0])
        self.assertIn("INSERT INTO system_metrics", cursor.executed[2][0])

    def test_run_total_system_metrics_repairs_duplicate_logical_rows(self) -> None:
        cursor = FakeCursor(fetch_results=[[(19111, "(0,9)"), (19124, "(0,4)")]])

        rows_written = persist_system_metrics(cursor, self.build_run_total_metrics_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 5)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("tableoid::oid", cursor.executed[1][0])
        self.assertIn("ctid::text", cursor.executed[1][0])
        self.assertIn("DELETE FROM system_metrics", cursor.executed[2][0])
        self.assertIn("tableoid = %(survivor_tableoid)s::oid", cursor.executed[2][0])
        self.assertIn("ctid = %(survivor_ctid)s::tid", cursor.executed[2][0])
        self.assertEqual(cursor.executed[2][1]["survivor_tableoid"], 19111)
        self.assertEqual(cursor.executed[2][1]["survivor_ctid"], "(0,9)")
        self.assertIn("DELETE FROM system_metrics", cursor.executed[3][0])
        self.assertIn("tableoid = %(survivor_tableoid)s::oid", cursor.executed[3][0])
        self.assertIn("ctid = %(survivor_ctid)s::tid", cursor.executed[3][0])
        self.assertIn("INSERT INTO system_metrics", cursor.executed[4][0])

    def test_writer_record_system_metrics_rewrites_existing_logical_row(self) -> None:
        cursor = FakeCursor(fetch_results=[[(16432, "(0,7)")]])
        payload = build_writer_metric_payload(
            run_id="demo-run",
            topic="audio.features",
            metric_name="write_ms",
            metric_value=14.25,
            unit="ms",
            status="ok",
            partition=0,
            offset=12,
        )

        rows_written = persist_system_metrics(cursor, payload)

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 4)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("SELECT", cursor.executed[1][0])
        self.assertIn("DELETE FROM system_metrics", cursor.executed[2][0])
        self.assertIn("INSERT INTO system_metrics", cursor.executed[3][0])

    def test_processing_record_error_metrics_rewrite_existing_logical_row(self) -> None:
        cursor = FakeCursor(fetch_results=[[(16432, "(0,7)")]])

        rows_written = persist_system_metrics(cursor, self.build_processing_record_error_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 4)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("SELECT", cursor.executed[1][0])
        self.assertIn("DELETE FROM system_metrics", cursor.executed[2][0])
        self.assertIn("INSERT INTO system_metrics", cursor.executed[3][0])

    def test_writer_internal_metric_payload_uses_locked_labels_and_unit(self) -> None:
        payload = build_writer_metric_payload(
            run_id="demo-run",
            topic="audio.features",
            metric_name="write_ms",
            metric_value=14.25,
            unit="ms",
            status="ok",
            partition=0,
            offset=12,
        )

        self.assertEqual(payload.service_name, "writer")
        self.assertEqual(payload.metric_name, "write_ms")
        self.assertEqual(payload.metric_value, 14.25)
        self.assertEqual(payload.unit, "ms")
        self.assertEqual(
            payload.labels_json,
            {
                "scope": "writer_record",
                "topic": "audio.features",
                "status": "ok",
                "partition": 0,
                "offset": 12,
            },
        )


if __name__ == "__main__":
    unittest.main()
