"""Event publication helpers for the ingestion service."""

from __future__ import annotations

from typing import Protocol

from event_driven_audio_analytics.shared.contracts.topics import AUDIO_METADATA, AUDIO_SEGMENT_READY
from event_driven_audio_analytics.shared.kafka import serialize_envelope
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope, build_envelope


class ProducerLike(Protocol):
    """Minimal producer protocol used by the ingestion pipeline."""

    def produce(self, *, topic: str, value: bytes, key: bytes | None = None) -> None:
        """Publish a message payload."""

    def flush(self) -> int | None:
        """Flush any buffered messages."""


def build_metadata_event(payload: AudioMetadataPayload) -> EventEnvelope[AudioMetadataPayload]:
    """Wrap metadata payloads in the shared event envelope."""

    return build_envelope(event_type="audio.metadata", source_service="ingestion", payload=payload)


def build_segment_ready_event(
    payload: AudioSegmentReadyPayload,
) -> EventEnvelope[AudioSegmentReadyPayload]:
    """Wrap segment-ready payloads in the shared event envelope."""

    return build_envelope(
        event_type="audio.segment.ready",
        source_service="ingestion",
        payload=payload,
    )


def publish_metadata_event(
    producer: ProducerLike,
    payload: AudioMetadataPayload,
) -> EventEnvelope[AudioMetadataPayload]:
    """Publish one audio.metadata envelope with the canonical track key."""

    envelope = build_metadata_event(payload)
    producer.produce(
        topic=AUDIO_METADATA,
        key=str(payload.track_id).encode("utf-8"),
        value=serialize_envelope(envelope),
    )
    return envelope


def publish_segment_ready_event(
    producer: ProducerLike,
    payload: AudioSegmentReadyPayload,
) -> EventEnvelope[AudioSegmentReadyPayload]:
    """Publish one audio.segment.ready envelope with the canonical track key."""

    envelope = build_segment_ready_event(payload)
    producer.produce(
        topic=AUDIO_SEGMENT_READY,
        key=str(payload.track_id).encode("utf-8"),
        value=serialize_envelope(envelope),
    )
    return envelope
