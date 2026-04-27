"""Shared event-envelope model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Generic, TypeVar

from event_driven_audio_analytics.shared.ids import generate_event_id
from event_driven_audio_analytics.shared.models.payload_validation import validate_payload_contract
from event_driven_audio_analytics.shared.storage import validate_run_id


PayloadT = TypeVar("PayloadT")
EVENT_VERSION = "v1"
CANONICAL_ENVELOPE_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "event_version",
        "trace_id",
        "run_id",
        "produced_at",
        "source_service",
        "idempotency_key",
        "payload",
    }
)
SOURCE_SERVICE_BY_EVENT_TYPE = {
    "audio.metadata": {"ingestion"},
    "audio.segment.ready": {"ingestion"},
    "audio.features": {"processing"},
    "system.metrics": {"ingestion", "processing", "writer"},
}


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp in RFC 3339 form."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _payload_to_dict(payload: PayloadT | dict[str, object]) -> dict[str, object]:
    """Normalize a dataclass or mapping payload into a dictionary."""

    if is_dataclass(payload):
        payload_data = asdict(payload)
    elif isinstance(payload, dict):
        payload_data = dict(payload)
    else:
        raise TypeError("Envelope payload must be a dataclass instance or dictionary.")

    return {
        field_name: field_value
        for field_name, field_value in payload_data.items()
        if field_value is not None
    }


def _require_string(payload_data: dict[str, object], field_name: str) -> str:
    """Read a non-empty string field from payload data."""

    value = payload_data.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Envelope payload must expose a non-empty {field_name}.")
    return value


def _require_envelope_string(envelope: dict[str, object], field_name: str) -> str:
    """Read a non-empty string field from envelope data."""

    value = envelope.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Envelope must expose a non-empty {field_name}.")
    return value


def _require_integer(payload_data: dict[str, object], field_name: str) -> int:
    """Read an integer field from payload data."""

    value = payload_data.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Envelope payload must expose an integer {field_name}.")
    return value


def _require_utc_timestamp(value: object, field_name: str) -> str:
    """Validate that a string field is an RFC 3339 UTC timestamp."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"Envelope must expose a non-empty {field_name}.")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Envelope field {field_name} must be a valid RFC 3339 timestamp."
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Envelope field {field_name} must be UTC.")

    return value


def _labels_digest(labels: object) -> str:
    """Hash labels_json using the canonical JSON form expected by the contract."""

    return sha256(
        json.dumps(labels, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def validate_envelope_dict(
    envelope: dict[str, object],
    *,
    expected_event_type: str | None = None,
) -> dict[str, object]:
    """Validate shared semantic invariants for a decoded event envelope."""

    envelope_fields = set(envelope)
    missing_fields = CANONICAL_ENVELOPE_FIELDS - envelope_fields
    if missing_fields:
        raise ValueError(
            "Envelope missing required top-level fields: "
            f"{', '.join(sorted(missing_fields))}."
        )

    extra_fields = envelope_fields - CANONICAL_ENVELOPE_FIELDS
    if extra_fields:
        raise ValueError(
            "Envelope contains unsupported top-level fields: "
            f"{', '.join(sorted(extra_fields))}."
        )

    _require_envelope_string(envelope, "event_id")

    event_version = envelope.get("event_version")
    if event_version != EVENT_VERSION:
        raise ValueError(f"Unsupported event_version: {event_version!r}.")

    event_type = _require_envelope_string(envelope, "event_type")
    if expected_event_type is not None and event_type != expected_event_type:
        raise ValueError("Envelope event_type does not match Kafka topic.")

    run_id = _require_envelope_string(envelope, "run_id")
    validate_run_id(run_id)
    trace_id = _require_envelope_string(envelope, "trace_id")
    if not trace_id.startswith(f"run/{run_id}/"):
        raise ValueError("Envelope trace_id must be scoped to the top-level run_id.")

    _require_utc_timestamp(envelope.get("produced_at"), "produced_at")

    source_service = _require_envelope_string(envelope, "source_service")
    allowed_source_services = SOURCE_SERVICE_BY_EVENT_TYPE.get(event_type)
    if allowed_source_services is not None and source_service not in allowed_source_services:
        raise ValueError(
            "Envelope source_service is not valid for the event_type."
        )

    idempotency_key = _require_envelope_string(envelope, "idempotency_key")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Envelope payload must be a JSON object.")

    payload_run_id = payload.get("run_id")
    if not isinstance(payload_run_id, str) or not payload_run_id:
        raise ValueError("Envelope payload must expose a non-empty run_id.")
    if payload_run_id != run_id:
        raise ValueError("Envelope run_id must match payload run_id.")
    validate_payload_contract(event_type, payload)

    expected_idempotency_key = build_idempotency_key(
        event_type=event_type,
        payload=payload,
        event_version=EVENT_VERSION,
    )
    if idempotency_key != expected_idempotency_key:
        raise ValueError("Envelope idempotency_key does not match the canonical v1 identity.")

    return payload


def build_trace_id(payload: PayloadT | dict[str, object], source_service: str) -> str:
    """Derive a stable trace identifier for one logical processing chain."""

    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")
    validate_run_id(run_id)
    track_id = payload_data.get("track_id")
    if isinstance(track_id, int) and not isinstance(track_id, bool):
        return f"run/{run_id}/track/{track_id}"

    service_name = payload_data.get("service_name")
    if isinstance(service_name, str) and service_name:
        return f"run/{run_id}/service/{service_name}"

    return f"run/{run_id}/service/{source_service}"


def build_idempotency_key(
    event_type: str,
    payload: PayloadT | dict[str, object],
    event_version: str = EVENT_VERSION,
) -> str:
    """Derive a deterministic idempotency key from event logical identity."""

    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")
    validate_run_id(run_id)

    if event_type == "audio.metadata":
        track_id = _require_integer(payload_data, "track_id")
        return f"{event_type}:{event_version}:{run_id}:{track_id}"

    if event_type in {"audio.segment.ready", "audio.features"}:
        track_id = _require_integer(payload_data, "track_id")
        segment_idx = _require_integer(payload_data, "segment_idx")
        return f"{event_type}:{event_version}:{run_id}:{track_id}:{segment_idx}"

    if event_type == "system.metrics":
        service_name = _require_string(payload_data, "service_name")
        metric_name = _require_string(payload_data, "metric_name")
        labels = payload_data.get("labels_json", {})
        labels_digest = _labels_digest(labels)
        if isinstance(labels, dict) and labels.get("scope") in {
            "run_total",
            "processing_record",
            "writer_record",
        }:
            scope = str(labels["scope"])
            return (
                f"{event_type}:{event_version}:{run_id}:{service_name}:"
                f"{metric_name}:{scope}:{labels_digest}"
            )

        ts = _require_string(payload_data, "ts")
        return (
            f"{event_type}:{event_version}:{run_id}:{service_name}:"
            f"{metric_name}:{ts}:{labels_digest}"
        )

    raise ValueError(f"Unsupported event_type for idempotency key generation: {event_type}.")


@dataclass(slots=True)
class EventEnvelope(Generic[PayloadT]):
    """Generic event envelope for topic payloads."""

    event_id: str
    event_type: str
    event_version: str
    trace_id: str
    run_id: str
    produced_at: str
    source_service: str
    idempotency_key: str
    payload: PayloadT

    def to_dict(self) -> dict[str, object]:
        payload = _payload_to_dict(self.payload)

        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "produced_at": self.produced_at,
            "source_service": self.source_service,
            "idempotency_key": self.idempotency_key,
            "payload": payload,
        }


def build_envelope(
    event_type: str,
    source_service: str,
    payload: PayloadT,
    *,
    event_id: str | None = None,
    produced_at: str | None = None,
    trace_id: str | None = None,
) -> EventEnvelope[PayloadT]:
    """Build a canonical v1 event envelope from a typed payload."""

    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")
    validate_run_id(run_id)
    validate_payload_contract(event_type, payload_data)
    envelope_trace_id = trace_id or build_trace_id(payload_data, source_service=source_service)
    if not isinstance(envelope_trace_id, str) or not envelope_trace_id:
        raise ValueError("Envelope trace_id override must be a non-empty string.")
    if not envelope_trace_id.startswith(f"run/{run_id}/"):
        raise ValueError("Envelope trace_id override must stay scoped to the top-level run_id.")

    return EventEnvelope(
        event_id=event_id or generate_event_id(),
        event_type=event_type,
        event_version=EVENT_VERSION,
        trace_id=envelope_trace_id,
        run_id=run_id,
        produced_at=produced_at or _utc_now_iso(),
        source_service=source_service,
        idempotency_key=build_idempotency_key(
            event_type=event_type,
            payload=payload_data,
            event_version=EVENT_VERSION,
        ),
        payload=payload,
    )
