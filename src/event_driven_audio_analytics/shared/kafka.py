"""Kafka client configuration helpers."""

from __future__ import annotations

from collections.abc import Iterable
import json

from confluent_kafka import Consumer, Producer

from event_driven_audio_analytics.shared.models.envelope import EventEnvelope


def producer_config(bootstrap_servers: str, client_id: str) -> dict[str, object]:
    """Return shared producer configuration."""

    return {
        "bootstrap.servers": bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
    }


def build_producer(bootstrap_servers: str, client_id: str) -> Producer:
    """Build a Kafka producer with the shared runtime defaults."""

    return Producer(producer_config(bootstrap_servers=bootstrap_servers, client_id=client_id))


def consumer_config(
    bootstrap_servers: str,
    group_id: str,
    client_id: str,
    auto_offset_reset: str = "earliest",
) -> dict[str, object]:
    """Return shared consumer configuration."""

    return {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "client.id": client_id,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": False,
    }


def build_consumer(
    bootstrap_servers: str,
    group_id: str,
    client_id: str,
    topics: Iterable[str],
    auto_offset_reset: str = "earliest",
) -> Consumer:
    """Build and subscribe a Kafka consumer with shared runtime defaults."""

    consumer = Consumer(
        consumer_config(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            auto_offset_reset=auto_offset_reset,
        )
    )
    consumer.subscribe(list(topics))
    return consumer


def serialize_envelope(envelope: EventEnvelope[object] | dict[str, object]) -> bytes:
    """Encode an envelope payload for Kafka transport."""

    message: dict[str, object]
    if isinstance(envelope, EventEnvelope):
        message = envelope.to_dict()
    else:
        message = envelope

    return json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize_envelope(payload: bytes | str) -> dict[str, object]:
    """Decode a Kafka value into an envelope dictionary."""

    raw_payload = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    message = json.loads(raw_payload)
    if not isinstance(message, dict):
        raise ValueError("Kafka message must decode to an object envelope.")
    return message
