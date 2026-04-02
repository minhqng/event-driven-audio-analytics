"""Pipeline outline for the writer service."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from event_driven_audio_analytics.shared.contracts.topics import AUDIO_DLQ
from event_driven_audio_analytics.shared.db import transaction_cursor
from event_driven_audio_analytics.shared.kafka import deserialize_envelope

from .config import WriterSettings
from .modules.checkpoint_store import build_checkpoint_record, persist_checkpoint
from .modules.consumer import ConsumedRecord, build_writer_consumer, poll_record
from .modules.offset_manager import build_commit_decision
from .modules.persistence import persist_envelope_payload


@dataclass(slots=True)
class WriterPipeline:
    """Consume Kafka envelopes and persist them to TimescaleDB."""

    settings: WriterSettings

    def describe(self) -> list[str]:
        return [
            "consume audio.metadata, audio.features, and system.metrics events",
            "persist track metadata, feature summaries, and system metrics",
            "upsert feature summaries using the logical key (run_id, track_id, segment_idx)",
            "update run checkpoints after successful persistence",
            "commit Kafka offsets only after persistence and checkpoint update",
        ]

    def run(self) -> None:
        logger = logging.getLogger(self.settings.base.service_name)
        consumer = build_writer_consumer(self.settings)

        try:
            while True:
                try:
                    record = poll_record(consumer)
                except Exception:
                    logger.exception("Writer failed while polling Kafka.")
                    continue

                if record is None:
                    continue

                try:
                    rows_written, checkpoints_ready = self._persist_record(record)
                    decision = build_commit_decision(
                        rows_written=rows_written,
                        checkpoints_ready=checkpoints_ready,
                    )
                    if not decision.commit_allowed:
                        raise RuntimeError(decision.reason)

                    consumer.commit(message=record.message, asynchronous=False)
                    logger.info(
                        "Persisted topic=%s partition=%s offset=%s rows=%s",
                        record.topic,
                        record.partition,
                        record.offset,
                        rows_written,
                    )
                except Exception:
                    logger.exception(
                        "Writer failed for topic=%s partition=%s offset=%s. "
                        "Leaving the record uncommitted because %s is reserved but not implemented yet.",
                        record.topic,
                        record.partition,
                        record.offset,
                        AUDIO_DLQ,
                    )
        finally:
            consumer.close()

    def _persist_record(self, record: ConsumedRecord) -> tuple[int, bool]:
        envelope = deserialize_envelope(record.value)
        if envelope.get("schema_version") != "v1":
            raise ValueError(f"Unsupported schema version for topic {record.topic}.")
        if envelope.get("event_type") != record.topic:
            raise ValueError("Envelope event_type does not match Kafka topic.")

        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Envelope payload must be a JSON object.")

        with transaction_cursor(self.settings.database) as (_, cursor):
            rows_written = persist_envelope_payload(
                cursor=cursor,
                topic=record.topic,
                payload_data=payload,
            )
            checkpoint_record = build_checkpoint_record(
                consumer_group=self.settings.consumer_group,
                topic_name=record.topic,
                partition_id=record.partition,
                run_id=str(payload["run_id"]),
                last_committed_offset=record.offset,
            )
            checkpoint_rows = persist_checkpoint(cursor, checkpoint_record)

        return rows_written, checkpoint_rows > 0
