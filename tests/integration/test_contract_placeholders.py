from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas" / "events"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "events" / "v1"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class ContractPlaceholderTests(unittest.TestCase):
    def assert_fixture_matches_required_fields(self, schema_name: str, fixture_name: str) -> None:
        schema = load_json(SCHEMAS_DIR / schema_name)
        fixture = load_json(FIXTURES_DIR / fixture_name)
        required_top_level = schema["required"]

        for field_name in required_top_level:
            self.assertIn(field_name, fixture)

        payload_schema = schema["properties"]["payload"]
        for field_name in payload_schema["required"]:
            self.assertIn(field_name, fixture["payload"])

    def test_audio_metadata_fixture_matches_schema_shape(self) -> None:
        self.assert_fixture_matches_required_fields("audio.metadata.v1.json", "audio.metadata.valid.json")

    def test_audio_segment_ready_fixture_matches_schema_shape(self) -> None:
        self.assert_fixture_matches_required_fields(
            "audio.segment.ready.v1.json",
            "audio.segment.ready.valid.json",
        )

    def test_audio_features_fixture_matches_schema_shape(self) -> None:
        self.assert_fixture_matches_required_fields("audio.features.v1.json", "audio.features.valid.json")

    def test_system_metrics_fixture_matches_schema_shape(self) -> None:
        self.assert_fixture_matches_required_fields("system.metrics.v1.json", "system.metrics.valid.json")


if __name__ == "__main__":
    unittest.main()
