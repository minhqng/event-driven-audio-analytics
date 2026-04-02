from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.writer.modules.persistence import persist_audio_features


class FakeCursor:
    def __init__(self, fetch_results: list[list[tuple[int]]] | None = None) -> None:
        self.fetch_results = list(fetch_results or [])
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))
        self.rowcount = 1

    def fetchall(self) -> list[tuple[int]]:
        if not self.fetch_results:
            return []
        return self.fetch_results.pop(0)


class WriterPersistenceTests(unittest.TestCase):
    def build_payload(self) -> AudioFeaturesPayload:
        return AudioFeaturesPayload(
            ts="2026-03-24T00:00:10Z",
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

    def test_audio_features_inserts_when_natural_key_is_missing(self) -> None:
        cursor = FakeCursor(fetch_results=[[]])

        rows_written = persist_audio_features(cursor, self.build_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 3)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("UPDATE audio_features", cursor.executed[1][0])
        self.assertIn("INSERT INTO audio_features", cursor.executed[2][0])

    def test_audio_features_updates_when_natural_key_exists(self) -> None:
        cursor = FakeCursor(fetch_results=[[(1,)]])

        rows_written = persist_audio_features(cursor, self.build_payload())

        self.assertEqual(rows_written, 1)
        self.assertEqual(len(cursor.executed), 2)
        self.assertIn("pg_advisory_xact_lock", cursor.executed[0][0])
        self.assertIn("UPDATE audio_features", cursor.executed[1][0])

    def test_audio_features_fails_when_natural_key_matches_multiple_rows(self) -> None:
        cursor = FakeCursor(fetch_results=[[(1,), (1,)]])

        with self.assertRaises(ValueError):
            persist_audio_features(cursor, self.build_payload())


if __name__ == "__main__":
    unittest.main()
