"""Event publication placeholders for the processing service."""

from __future__ import annotations

from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope, build_envelope
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


def build_audio_features_event(
    payload: AudioFeaturesPayload,
) -> EventEnvelope[AudioFeaturesPayload]:
    """Wrap feature payloads in the shared event envelope."""

    return build_envelope(event_type="audio.features", produced_by="processing", payload=payload)


def build_system_metrics_event(
    payload: SystemMetricsPayload,
) -> EventEnvelope[SystemMetricsPayload]:
    """Wrap metric payloads in the shared event envelope."""

    return build_envelope(event_type="system.metrics", produced_by="processing", payload=payload)
