"""Kafka-consumption placeholders for the writer service."""

from __future__ import annotations

from dataclasses import dataclass

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from event_driven_audio_analytics.shared.contracts.topics import WRITER_INPUT_TOPICS
from event_driven_audio_analytics.shared.kafka import build_consumer
from event_driven_audio_analytics.writer.config import WriterSettings


@dataclass(slots=True)
class ConsumedRecord:
    """A minimal consumed Kafka record placeholder."""

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
    )


def poll_record(consumer: Consumer, timeout_s: float = 1.0) -> ConsumedRecord | None:
    """Poll a single Kafka record and decode the shared envelope."""

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
