from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = REPO_ROOT / "infra" / "sql" / "002_core_tables.sql"


class WriterSchemaPlaceholderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_track_metadata_is_regular_table(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS track_metadata", self.sql)
        self.assertIn("PRIMARY KEY (run_id, track_id)", self.sql)

    def test_audio_features_mentions_logical_key_columns(self) -> None:
        self.assertIn("run_id TEXT NOT NULL", self.sql)
        self.assertIn("track_id BIGINT NOT NULL", self.sql)
        self.assertIn("segment_idx INTEGER NOT NULL", self.sql)
        self.assertIn("SELECT create_hypertable('audio_features'", self.sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_audio_features_lookup", self.sql)

    def test_system_metrics_shape_is_fixed(self) -> None:
        self.assertIn("service_name TEXT NOT NULL", self.sql)
        self.assertIn("metric_name TEXT NOT NULL", self.sql)
        self.assertIn("metric_value DOUBLE PRECISION NOT NULL", self.sql)
        self.assertIn("labels_json JSONB NOT NULL", self.sql)
        self.assertIn("SELECT create_hypertable('system_metrics'", self.sql)

    def test_run_checkpoints_is_regular_table(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS run_checkpoints", self.sql)
        self.assertIn("PRIMARY KEY (consumer_group, topic_name, partition_id)", self.sql)

    def test_welford_snapshots_table_exists(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS welford_snapshots", self.sql)
        self.assertIn("PRIMARY KEY (run_id, service_name, metric_name)", self.sql)


if __name__ == "__main__":
    unittest.main()
