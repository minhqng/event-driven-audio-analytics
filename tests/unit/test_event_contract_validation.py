from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.kafka import deserialize_envelope, serialize_envelope
from event_driven_audio_analytics.shared.models.envelope import validate_envelope_dict


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas" / "events"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "events" / "v1"
FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_validator(schema_name: str) -> Draft202012Validator:
    schema = load_json(SCHEMAS_DIR / schema_name)
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


class EventContractValidationTests(unittest.TestCase):
    def test_valid_v1_fixtures_round_trip_and_validate(self) -> None:
        cases = (
            ("audio.metadata.v1.json", "audio.metadata.valid.json"),
            ("audio.segment.ready.v1.json", "audio.segment.ready.valid.json"),
            ("audio.features.v1.json", "audio.features.valid.json"),
            ("system.metrics.v1.json", "system.metrics.valid.json"),
            ("system.metrics.v1.json", "system.metrics.run_total.valid.json"),
        )

        for schema_name, fixture_name in cases:
            with self.subTest(fixture=fixture_name):
                envelope = load_json(FIXTURES_DIR / fixture_name)
                round_trip = deserialize_envelope(serialize_envelope(envelope))

                self.assertEqual(round_trip, envelope)
                load_validator(schema_name).validate(round_trip)
                validate_envelope_dict(
                    round_trip,
                    expected_event_type=str(round_trip["event_type"]),
                )

    def test_missing_required_field_fails_validation(self) -> None:
        validator = load_validator("audio.metadata.v1.json")
        envelope = load_json(FIXTURES_DIR / "audio.metadata.missing-trace-id.json")

        with self.assertRaises(ValidationError):
            validator.validate(envelope)

    def test_version_mismatch_fails_validation(self) -> None:
        validator = load_validator("audio.features.v1.json")
        envelope = load_json(FIXTURES_DIR / "audio.features.version-mismatch.json")

        with self.assertRaises(ValidationError):
            validator.validate(envelope)

    def test_segment_ready_payload_type_mismatch_fails_validation(self) -> None:
        validator = load_validator("audio.segment.ready.v1.json")
        envelope = load_json(FIXTURES_DIR / "audio.segment.ready.payload-type-mismatch.json")

        with self.assertRaises(ValidationError):
            validator.validate(envelope)

    def test_system_metrics_payload_type_mismatch_fails_validation(self) -> None:
        validator = load_validator("system.metrics.v1.json")
        envelope = load_json(FIXTURES_DIR / "system.metrics.payload-type-mismatch.json")

        with self.assertRaises(ValidationError):
            validator.validate(envelope)

    def test_run_id_mismatch_fails_semantic_validation(self) -> None:
        validator = load_validator("audio.metadata.v1.json")
        envelope = load_json(FIXTURES_DIR / "audio.metadata.run-id-mismatch.json")

        validator.validate(envelope)

        with self.assertRaisesRegex(ValueError, "run_id"):
            validate_envelope_dict(envelope, expected_event_type="audio.metadata")

    def test_unsafe_run_id_fails_schema_validation(self) -> None:
        validator = load_validator("audio.metadata.v1.json")

        for run_id in ("../demo", "demo run"):
            with self.subTest(run_id=run_id):
                envelope = load_json(FIXTURES_DIR / "audio.metadata.valid.json")
                envelope["run_id"] = run_id
                envelope["payload"]["run_id"] = run_id

                with self.assertRaises(ValidationError):
                    validator.validate(envelope)

    def test_missing_required_top_level_fields_fail_semantic_validation(self) -> None:
        required_fields = (
            "event_id",
            "trace_id",
            "produced_at",
            "source_service",
            "idempotency_key",
        )

        for field_name in required_fields:
            with self.subTest(field=field_name):
                envelope = load_json(FIXTURES_DIR / "audio.features.valid.json")
                envelope.pop(field_name)

                with self.assertRaisesRegex(ValueError, field_name):
                    validate_envelope_dict(envelope, expected_event_type="audio.features")

    def test_wrong_idempotency_key_fails_semantic_validation(self) -> None:
        envelope = load_json(FIXTURES_DIR / "audio.features.valid.json")
        envelope["idempotency_key"] = "audio.features:v1:demo-run:2:999"

        with self.assertRaisesRegex(ValueError, "idempotency_key"):
            validate_envelope_dict(envelope, expected_event_type="audio.features")

    def test_non_finite_feature_payload_fails_runtime_validation(self) -> None:
        envelope = load_json(FIXTURES_DIR / "audio.features.valid.json")
        envelope["payload"]["rms"] = float("nan")

        with self.assertRaisesRegex(ValueError, "finite"):
            validate_envelope_dict(envelope, expected_event_type="audio.features")

    def test_deserialize_rejects_non_json_numeric_constants(self) -> None:
        raw_message = (
            '{"event_id":"e","event_type":"audio.features","event_version":"v1",'
            '"trace_id":"run/demo-run/track/2","run_id":"demo-run",'
            '"produced_at":"2026-04-02T00:00:00Z","source_service":"processing",'
            '"idempotency_key":"audio.features:v1:demo-run:2:0",'
            '"payload":{"ts":"2026-04-02T00:00:00Z","run_id":"demo-run",'
            '"track_id":2,"segment_idx":0,"artifact_uri":"/app/artifacts/runs/demo-run/segments/2/0.wav",'
            '"checksum":"x","rms":NaN,"silent_flag":false,"mel_bins":128,'
            '"mel_frames":300,"processing_ms":1.0}}'
        )

        with self.assertRaisesRegex(ValueError, "non-JSON numeric constant"):
            deserialize_envelope(raw_message)

    def test_serialize_rejects_non_finite_numbers(self) -> None:
        envelope = load_json(FIXTURES_DIR / "audio.features.valid.json")
        envelope["payload"]["rms"] = float("inf")

        with self.assertRaises(ValueError):
            serialize_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
