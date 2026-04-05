"""Thin persistence dispatcher for the writer service."""

from __future__ import annotations

from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_FEATURES,
    AUDIO_METADATA,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload
from .upsert_features import persist_audio_features
from .upsert_metadata import TRACK_METADATA_UPSERT, persist_track_metadata
from .write_metrics import persist_system_metrics


class WriterPayloadValidationError(RuntimeError):
    """Raised when a Kafka payload cannot be coerced into the writer contract."""

    pass


def _build_payload(model_type: type[object], payload_data: dict[str, object], *, topic: str) -> object:
    """Coerce one envelope payload into its typed writer model."""

    try:
        return model_type(**payload_data)
    except (TypeError, ValueError) as exc:
        raise WriterPayloadValidationError(
            f"Writer payload for topic {topic} does not match the canonical v1 contract."
        ) from exc


def persist_envelope_payload(
    cursor: object,
    topic: str,
    payload_data: dict[str, object],
) -> int:
    """Persist one decoded envelope payload based on the Kafka topic."""

    if topic == AUDIO_METADATA:
        return persist_track_metadata(
            cursor,
            _build_payload(AudioMetadataPayload, payload_data, topic=topic),
        )
    if topic == AUDIO_FEATURES:
        return persist_audio_features(
            cursor,
            _build_payload(AudioFeaturesPayload, payload_data, topic=topic),
        )
    if topic == SYSTEM_METRICS:
        return persist_system_metrics(
            cursor,
            _build_payload(SystemMetricsPayload, payload_data, topic=topic),
        )
    raise ValueError(f"Writer cannot persist unsupported topic: {topic}.")
