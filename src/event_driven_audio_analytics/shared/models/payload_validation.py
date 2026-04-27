"""Runtime payload validation for canonical event contract v1."""

from __future__ import annotations

from datetime import datetime, timedelta
import math

from event_driven_audio_analytics.shared.storage import validate_run_id


def _require_string(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Payload field {field_name} must be a non-empty string.")
    return value


def _require_integer(payload: dict[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Payload field {field_name} must be an integer.")
    return value


def _require_boolean(payload: dict[str, object], field_name: str) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"Payload field {field_name} must be a boolean.")
    return value


def _reject_non_finite_json_numbers(value: object, path: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Payload field {path} must be finite.")
    if isinstance(value, dict):
        for key, nested_value in value.items():
            _reject_non_finite_json_numbers(nested_value, f"{path}.{key}")
    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            _reject_non_finite_json_numbers(nested_value, f"{path}[{index}]")


def _require_finite_number(
    payload: dict[str, object],
    field_name: str,
    *,
    minimum: float | None = None,
    exclusive_minimum: float | None = None,
) -> float:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Payload field {field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Payload field {field_name} must be finite.")
    if minimum is not None and number < minimum:
        raise ValueError(f"Payload field {field_name} must be >= {minimum}.")
    if exclusive_minimum is not None and number <= exclusive_minimum:
        raise ValueError(f"Payload field {field_name} must be > {exclusive_minimum}.")
    return number


def _require_utc_timestamp(payload: dict[str, object], field_name: str) -> str:
    value = _require_string(payload, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Payload field {field_name} must be a valid RFC 3339 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Payload field {field_name} must be UTC.")
    return value


def _validate_allowed_fields(
    payload: dict[str, object],
    *,
    required: set[str],
    optional: set[str],
) -> None:
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Payload missing required fields: {', '.join(sorted(missing))}.")
    extra = set(payload) - required - optional
    if extra:
        raise ValueError(f"Payload contains unsupported fields: {', '.join(sorted(extra))}.")


def _validate_optional_string(payload: dict[str, object], field_name: str) -> None:
    if field_name in payload:
        _require_string(payload, field_name)


def _validate_audio_metadata(payload: dict[str, object]) -> None:
    _validate_allowed_fields(
        payload,
        required={
            "run_id",
            "track_id",
            "artist_id",
            "genre",
            "source_audio_uri",
            "validation_status",
            "duration_s",
        },
        optional={"subset", "manifest_uri", "checksum"},
    )
    validate_run_id(_require_string(payload, "run_id"))
    _require_integer(payload, "track_id")
    _require_integer(payload, "artist_id")
    _require_string(payload, "genre")
    _require_string(payload, "source_audio_uri")
    _require_string(payload, "validation_status")
    _require_finite_number(payload, "duration_s", exclusive_minimum=0.0)
    if "subset" in payload and payload["subset"] != "small":
        raise ValueError("Payload field subset must be 'small' when present.")
    _validate_optional_string(payload, "manifest_uri")
    _validate_optional_string(payload, "checksum")


def _validate_audio_segment_ready(payload: dict[str, object]) -> None:
    _validate_allowed_fields(
        payload,
        required={
            "run_id",
            "track_id",
            "segment_idx",
            "artifact_uri",
            "checksum",
            "sample_rate",
            "duration_s",
            "is_last_segment",
        },
        optional={"manifest_uri"},
    )
    validate_run_id(_require_string(payload, "run_id"))
    _require_integer(payload, "track_id")
    _require_integer(payload, "segment_idx")
    _require_string(payload, "artifact_uri")
    _require_string(payload, "checksum")
    sample_rate = _require_integer(payload, "sample_rate")
    if sample_rate < 1:
        raise ValueError("Payload field sample_rate must be >= 1.")
    _require_finite_number(payload, "duration_s", exclusive_minimum=0.0)
    _require_boolean(payload, "is_last_segment")
    _validate_optional_string(payload, "manifest_uri")


def _validate_audio_features(payload: dict[str, object]) -> None:
    _validate_allowed_fields(
        payload,
        required={
            "ts",
            "run_id",
            "track_id",
            "segment_idx",
            "artifact_uri",
            "checksum",
            "rms",
            "silent_flag",
            "mel_bins",
            "mel_frames",
            "processing_ms",
        },
        optional={"manifest_uri"},
    )
    _require_utc_timestamp(payload, "ts")
    validate_run_id(_require_string(payload, "run_id"))
    _require_integer(payload, "track_id")
    _require_integer(payload, "segment_idx")
    _require_string(payload, "artifact_uri")
    _require_string(payload, "checksum")
    _require_finite_number(payload, "rms")
    _require_boolean(payload, "silent_flag")
    if _require_integer(payload, "mel_bins") < 1:
        raise ValueError("Payload field mel_bins must be >= 1.")
    if _require_integer(payload, "mel_frames") < 1:
        raise ValueError("Payload field mel_frames must be >= 1.")
    _require_finite_number(payload, "processing_ms", minimum=0.0)
    _validate_optional_string(payload, "manifest_uri")


def _validate_system_metrics(payload: dict[str, object]) -> None:
    _validate_allowed_fields(
        payload,
        required={"ts", "run_id", "service_name", "metric_name", "metric_value"},
        optional={"labels_json", "unit"},
    )
    _require_utc_timestamp(payload, "ts")
    validate_run_id(_require_string(payload, "run_id"))
    _require_string(payload, "service_name")
    _require_string(payload, "metric_name")
    _require_finite_number(payload, "metric_value")
    labels = payload.get("labels_json", {})
    if not isinstance(labels, dict):
        raise ValueError("Payload field labels_json must be an object when present.")
    _validate_optional_string(payload, "unit")


PAYLOAD_VALIDATORS = dict(
    audio_metadata=_validate_audio_metadata,
    audio_segment_ready=_validate_audio_segment_ready,
    audio_features=_validate_audio_features,
    system_metrics=_validate_system_metrics,
)


def validate_payload_contract(event_type: str, payload: dict[str, object]) -> None:
    """Validate topic-specific payload fields before runtime persistence/processing."""

    _reject_non_finite_json_numbers(payload, "payload")
    validator = PAYLOAD_VALIDATORS.get(event_type.replace(".", "_"))
    if validator is None:
        raise ValueError(f"Unsupported event_type for payload validation: {event_type}.")
    validator(payload)
