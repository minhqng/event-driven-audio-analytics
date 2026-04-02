"""Event publication placeholders for the ingestion service."""

from __future__ import annotations

from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope, build_envelope


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
