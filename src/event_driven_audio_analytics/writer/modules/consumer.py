"""Kafka consumption helpers for the writer service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.contracts.topics import WRITER_INPUT_TOPICS
from event_driven_audio_analytics.shared.kafka import build_consumer
from event_driven_audio_analytics.writer.config import WriterSettings

if TYPE_CHECKING:
    from confluent_kafka import Consumer, Message
else:
    Consumer = Any
    Message = Any


@dataclass(slots=True)
class ConsumedRecord:
    """A minimal consumed Kafka record for the writer loop."""

    topic: str
    partition: int
    offset: int
    value: bytes
    message: Message


def build_writer_consumer(settings: WriterSettings) -> Consumer:
    """Build a Kafka consumer subscribed to the writer input topics."""

    return build_consumer(
        bootstrap_servers=settings.base.kafka_bootstrap_servers,
        group_id=settings.consumer_group,
        client_id=settings.base.service_name,
        topics=WRITER_INPUT_TOPICS,
        auto_offset_reset=settings.auto_offset_reset,
        enable_auto_commit=False,
        enable_auto_offset_store=False,
        session_timeout_ms=settings.session_timeout_ms,
        max_poll_interval_ms=settings.max_poll_interval_ms,
        retry_backoff_ms=settings.consumer_retry_backoff_ms,
        retry_backoff_max_ms=settings.consumer_retry_backoff_max_ms,
    )


def poll_record(consumer: Consumer, timeout_s: float = 1.0) -> ConsumedRecord | None:
    """Poll a single Kafka record and decode the shared envelope."""

    from confluent_kafka import KafkaError, KafkaException

    message = consumer.poll(timeout_s)
    if message is None:
        return None

    if message.error() is not None:
        if message.error().code() in (
            KafkaError._PARTITION_EOF,
            KafkaError.UNKNOWN_TOPIC_OR_PART,
        ):
            return None
        raise KafkaException(message.error())

    return ConsumedRecord(
        topic=message.topic(),
        partition=message.partition(),
        offset=message.offset(),
        value=message.value() or b"",
        message=message,
    )
