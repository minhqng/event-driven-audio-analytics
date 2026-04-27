"""Kafka client configuration helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from time import monotonic
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.models.envelope import EventEnvelope

if TYPE_CHECKING:
    from confluent_kafka import Consumer, Message, Producer
else:
    Consumer = Any
    Message = Any
    Producer = Any


@dataclass(slots=True)
class KafkaDeliveryError(RuntimeError):
    """Raised when a Kafka publish is not durably acknowledged."""

    topic: str
    key: str | None
    reason: str

    def __str__(self) -> str:
        key_suffix = f" key={self.key}" if self.key is not None else ""
        return f"Kafka delivery failed for topic={self.topic}{key_suffix}: {self.reason}"


def producer_config(
    bootstrap_servers: str,
    client_id: str,
    *,
    retries: int = 10,
    retry_backoff_ms: int = 250,
    retry_backoff_max_ms: int = 5_000,
    delivery_timeout_ms: int = 120_000,
) -> dict[str, object]:
    """Return shared producer configuration."""

    return {
        "bootstrap.servers": bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
        "retries": retries,
        "retry.backoff.ms": retry_backoff_ms,
        "retry.backoff.max.ms": retry_backoff_max_ms,
        "delivery.timeout.ms": delivery_timeout_ms,
    }


def build_producer(
    bootstrap_servers: str,
    client_id: str,
    *,
    retries: int = 10,
    retry_backoff_ms: int = 250,
    retry_backoff_max_ms: int = 5_000,
    delivery_timeout_ms: int = 120_000,
) -> Producer:
    """Build a Kafka producer with the shared runtime defaults."""

    from confluent_kafka import Producer as KafkaProducer

    return KafkaProducer(
        producer_config(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            retries=retries,
            retry_backoff_ms=retry_backoff_ms,
            retry_backoff_max_ms=retry_backoff_max_ms,
            delivery_timeout_ms=delivery_timeout_ms,
        )
    )


def consumer_config(
    bootstrap_servers: str,
    group_id: str,
    client_id: str,
    auto_offset_reset: str = "earliest",
    *,
    enable_auto_commit: bool = False,
    enable_auto_offset_store: bool = False,
    session_timeout_ms: int | None = None,
    max_poll_interval_ms: int | None = None,
    retry_backoff_ms: int | None = None,
    retry_backoff_max_ms: int | None = None,
) -> dict[str, object]:
    """Return shared consumer configuration."""

    config: dict[str, object] = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "client.id": client_id,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": enable_auto_commit,
        "enable.auto.offset.store": enable_auto_offset_store,
    }
    if session_timeout_ms is not None:
        config["session.timeout.ms"] = session_timeout_ms
    if max_poll_interval_ms is not None:
        config["max.poll.interval.ms"] = max_poll_interval_ms
    if retry_backoff_ms is not None:
        config["retry.backoff.ms"] = retry_backoff_ms
    if retry_backoff_max_ms is not None:
        config["retry.backoff.max.ms"] = retry_backoff_max_ms
    return config


def build_consumer(
    bootstrap_servers: str,
    group_id: str,
    client_id: str,
    topics: Iterable[str],
    auto_offset_reset: str = "earliest",
    *,
    enable_auto_commit: bool = False,
    enable_auto_offset_store: bool = False,
    session_timeout_ms: int | None = None,
    max_poll_interval_ms: int | None = None,
    retry_backoff_ms: int | None = None,
    retry_backoff_max_ms: int | None = None,
) -> Consumer:
    """Build and subscribe a Kafka consumer with shared runtime defaults."""

    from confluent_kafka import Consumer as KafkaConsumer

    consumer = KafkaConsumer(
        consumer_config(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=enable_auto_commit,
            enable_auto_offset_store=enable_auto_offset_store,
            session_timeout_ms=session_timeout_ms,
            max_poll_interval_ms=max_poll_interval_ms,
            retry_backoff_ms=retry_backoff_ms,
            retry_backoff_max_ms=retry_backoff_max_ms,
        )
    )
    consumer.subscribe(list(topics))
    return consumer


def produce_and_wait(
    producer: Producer,
    *,
    topic: str,
    value: bytes,
    key: bytes | None = None,
    timeout_s: float = 30.0,
) -> None:
    """Produce one Kafka record and wait for a delivery report."""

    delivery_state: dict[str, object] = {
        "delivered": False,
        "error": None,
    }

    def on_delivery(error: object, _: Message | None) -> None:
        delivery_state["delivered"] = True
        delivery_state["error"] = error

    producer.produce(
        topic=topic,
        value=value,
        key=key,
        on_delivery=on_delivery,
    )

    flush = getattr(producer, "flush", None)
    if not callable(flush):
        raise TypeError("Kafka producer must expose flush(timeout) for delivery confirmation.")

    deadline = monotonic() + timeout_s
    remaining_messages: int | None = None
    while not bool(delivery_state["delivered"]):
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            break
        remaining_messages = flush(min(remaining_s, 0.5))
        if remaining_messages in (0, None) and bool(delivery_state["delivered"]):
            break

    decoded_key = key.decode("utf-8") if key is not None else None
    if not bool(delivery_state["delivered"]):
        raise KafkaDeliveryError(
            topic=topic,
            key=decoded_key,
            reason="timed out waiting for delivery report",
        )

    delivery_error = delivery_state["error"]
    if delivery_error is not None:
        raise KafkaDeliveryError(
            topic=topic,
            key=decoded_key,
            reason=str(delivery_error),
        )


def serialize_envelope(envelope: EventEnvelope[object] | dict[str, object]) -> bytes:
    """Encode an envelope payload for Kafka transport."""

    message: dict[str, object]
    if isinstance(envelope, EventEnvelope):
        message = envelope.to_dict()
    else:
        message = envelope

    return json.dumps(message, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize_envelope(payload: bytes | str) -> dict[str, object]:
    """Decode a Kafka value into an envelope dictionary."""

    def reject_non_json_constant(value: str) -> None:
        raise ValueError(f"Kafka message contains non-JSON numeric constant: {value}.")

    raw_payload = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    message = json.loads(raw_payload, parse_constant=reject_non_json_constant)
    if not isinstance(message, dict):
        raise ValueError("Kafka message must decode to an object envelope.")
    return message
