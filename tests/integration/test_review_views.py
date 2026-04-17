from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = REPO_ROOT / "infra" / "sql" / "004_review_views.sql"


class ReviewViewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_review_tracks_view_exists(self) -> None:
        self.assertIn("CREATE OR REPLACE VIEW vw_review_tracks AS", self.sql)
        self.assertIn("FROM track_metadata", self.sql)
        self.assertIn("LEFT JOIN LATERAL", self.sql)
        self.assertIn("FROM audio_features", self.sql)
        self.assertIn("WHERE audio_features.run_id = track_metadata.run_id", self.sql)

    def test_review_tracks_view_exposes_track_summary_fields(self) -> None:
        self.assertIn("segments_persisted", self.sql)
        self.assertIn("silent_segments", self.sql)
        self.assertIn("avg_rms", self.sql)
        self.assertIn("avg_processing_ms", self.sql)
        self.assertIn("track_state", self.sql)


if __name__ == "__main__":
    unittest.main()
