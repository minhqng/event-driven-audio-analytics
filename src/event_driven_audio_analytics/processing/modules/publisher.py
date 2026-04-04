"""Event publication placeholders for the processing service."""

from __future__ import annotations

from typing import Protocol

from event_driven_audio_analytics.shared.contracts.topics import AUDIO_FEATURES, SYSTEM_METRICS
from event_driven_audio_analytics.shared.kafka import produce_and_wait, serialize_envelope
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope, build_envelope
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


class ProducerLike(Protocol):
    """Minimal producer protocol used by the processing pipeline."""

    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: object | None = None,
    ) -> None:
        """Publish one Kafka message."""

    def flush(self, timeout: float | None = None) -> int | None:
        """Flush any buffered Kafka messages."""

    def poll(self, timeout: float = 0.0) -> int | None:
        """Serve delivery callbacks if the producer implementation requires it."""


def build_audio_features_event(
    payload: AudioFeaturesPayload,
    *,
    trace_id: str | None = None,
) -> EventEnvelope[AudioFeaturesPayload]:
    """Wrap feature payloads in the shared event envelope."""

    return build_envelope(
        event_type="audio.features",
        source_service="processing",
        payload=payload,
        trace_id=trace_id,
    )


def build_system_metrics_event(
    payload: SystemMetricsPayload,
    *,
    trace_id: str | None = None,
) -> EventEnvelope[SystemMetricsPayload]:
    """Wrap metric payloads in the shared event envelope."""

    return build_envelope(
        event_type="system.metrics",
        source_service="processing",
        payload=payload,
        trace_id=trace_id,
    )


def publish_audio_features_event(
    producer: ProducerLike,
    payload: AudioFeaturesPayload,
    *,
    trace_id: str | None = None,
    delivery_timeout_s: float = 30.0,
) -> EventEnvelope[AudioFeaturesPayload]:
    """Publish one audio.features envelope with the canonical track key."""

    envelope = build_audio_features_event(payload, trace_id=trace_id)
    produce_and_wait(
        producer,
        topic=AUDIO_FEATURES,
        key=str(payload.track_id).encode("utf-8"),
        value=serialize_envelope(envelope),
        timeout_s=delivery_timeout_s,
    )
    return envelope


def publish_system_metric_event(
    producer: ProducerLike,
    payload: SystemMetricsPayload,
    *,
    trace_id: str | None = None,
    delivery_timeout_s: float = 30.0,
) -> EventEnvelope[SystemMetricsPayload]:
    """Publish one system.metrics envelope keyed by service_name."""

    envelope = build_system_metrics_event(payload, trace_id=trace_id)
    produce_and_wait(
        producer,
        topic=SYSTEM_METRICS,
        key=payload.service_name.encode("utf-8"),
        value=serialize_envelope(envelope),
        timeout_s=delivery_timeout_s,
    )
    return envelope
