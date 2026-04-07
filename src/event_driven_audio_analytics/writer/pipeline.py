"""Week 6 writer pipeline from Kafka envelopes to TimescaleDB persistence."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.contracts.topics import AUDIO_DLQ
from event_driven_audio_analytics.shared.db import (
    close_database_pool,
    open_database_pool,
    pooled_transaction_cursor,
    transaction_cursor,
)
from event_driven_audio_analytics.shared.kafka import deserialize_envelope
from event_driven_audio_analytics.shared.logging import ServiceLoggerAdapter, get_service_logger
from event_driven_audio_analytics.shared.models.envelope import validate_envelope_dict
from event_driven_audio_analytics.shared.shutdown import install_shutdown_event

from .config import WriterSettings
from .modules.checkpoint_store import build_checkpoint_record, persist_checkpoint
from .modules.consumer import ConsumedRecord, build_writer_consumer, poll_record
from .modules.metrics import build_writer_metric_payload
from .modules.offset_manager import build_commit_decision
from .modules.persistence import (
    WriterPayloadValidationError,
    coerce_payload_model,
    persist_envelope_payload,
)
from .modules.upsert_features import AudioFeaturesNaturalKeyError
from .modules.write_metrics import persist_system_metrics

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool
else:
    ConnectionPool = Any


@dataclass(slots=True)
class WriterStageError(RuntimeError):
    """Describe one terminal writer-stage failure with a stable failure class."""

    failure_class: str
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(slots=True)
class WriterFailureDecision:
    """Stable failure classification for writer failure metrics and logs."""

    failure_class: str


@dataclass(slots=True)
class WriterRecordContext:
    """Structured context extracted from one consumed writer record."""

    run_id: str | None = None
    trace_id: str | None = None
    track_id: int | None = None
    segment_idx: int | None = None


@dataclass(slots=True)
class WriterPersistenceOutcome:
    """Persistence summary for one committed writer record."""

    rows_written: int
    checkpoint_rows: int
    context: WriterRecordContext
    write_ms: float


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

    def _bind_record_context(
        self,
        logger: ServiceLoggerAdapter,
        context: WriterRecordContext,
    ) -> ServiceLoggerAdapter:
        return logger.bind(
            run_id=context.run_id,
            trace_id=context.trace_id,
            track_id=context.track_id,
            segment_idx=context.segment_idx,
        )

    def _extract_record_context(self, envelope: dict[str, object] | None) -> WriterRecordContext:
        if not isinstance(envelope, dict):
            return WriterRecordContext()

        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        track_id = payload.get("track_id")
        segment_idx = payload.get("segment_idx")
        return WriterRecordContext(
            run_id=envelope.get("run_id") if isinstance(envelope.get("run_id"), str) else None,
            trace_id=envelope.get("trace_id") if isinstance(envelope.get("trace_id"), str) else None,
            track_id=track_id if isinstance(track_id, int) and not isinstance(track_id, bool) else None,
            segment_idx=(
                segment_idx
                if isinstance(segment_idx, int) and not isinstance(segment_idx, bool)
                else None
            ),
        )

    def _emit_failure_metric(
        self,
        *,
        pool: ConnectionPool | None,
        context: WriterRecordContext,
        record: ConsumedRecord,
        failure_class: str,
        logger: ServiceLoggerAdapter,
    ) -> None:
        if context.run_id is None or pool is None:
            return

        try:
            metric_payload = build_writer_metric_payload(
                run_id=context.run_id,
                topic=record.topic,
                metric_name="write_failures",
                metric_value=1.0,
                unit="count",
                status="error",
                partition=record.partition,
                offset=record.offset,
                failure_class=failure_class,
            )
            with pooled_transaction_cursor(pool) as (_, cursor):
                persist_system_metrics(cursor, metric_payload)
        except Exception:
            logger.bind(
                failure_class=failure_class,
                metric_name="write_failures",
                metric_value=1.0,
            ).exception("Writer failed to persist internal failure metrics.")

    def run(self, *, logger: ServiceLoggerAdapter | None = None) -> None:
        service_logger = logger or get_service_logger(
            self.settings.base.service_name,
            run_id=self.settings.base.run_id,
        )
        consumer = build_writer_consumer(self.settings)
        stop_requested, restore_handlers = install_shutdown_event()
        pool: ConnectionPool | None = None

        try:
            pool = open_database_pool(
                self.settings.database,
                min_size=self.settings.db_pool_min_size,
                max_size=self.settings.db_pool_max_size,
                timeout_s=self.settings.db_pool_timeout_s,
            )
            while not stop_requested.is_set():
                try:
                    record = poll_record(consumer, timeout_s=self.settings.poll_timeout_s)
                except Exception:
                    service_logger.bind(failure_class="poll_failed").exception(
                        "Writer failed while polling Kafka."
                    )
                    continue

                if record is None:
                    continue

                raw_envelope: dict[str, object] | None = None
                outcome: WriterPersistenceOutcome | None = None
                write_started_at = perf_counter()
                record_logger = service_logger.bind(
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                )
                try:
                    try:
                        raw_envelope = deserialize_envelope(record.value)
                    except ValueError as exc:
                        raise WriterStageError(
                            "envelope_invalid",
                            "Writer failed while decoding the current envelope.",
                        ) from exc
                    context = self._extract_record_context(raw_envelope)
                    record_logger = self._bind_record_context(record_logger, context)
                    outcome = self._persist_record(
                        record,
                        pool=pool,
                        raw_envelope=raw_envelope,
                        write_started_at=write_started_at,
                    )
                    try:
                        consumer.commit(message=record.message, asynchronous=False)
                    except Exception as exc:
                        raise WriterStageError(
                            "offset_commit_failed",
                            "Writer persisted the current record but failed to commit the Kafka offset.",
                        ) from exc
                except Exception as exc:
                    context = outcome.context if outcome is not None else self._extract_record_context(
                        raw_envelope
                    )
                    decision = classify_writer_failure(exc)
                    failure_logger = self._bind_record_context(record_logger, context).bind(
                        failure_class=decision.failure_class,
                    )
                    self._emit_failure_metric(
                        pool=pool,
                        context=context,
                        record=record,
                        failure_class=decision.failure_class,
                        logger=failure_logger,
                    )
                    failure_logger.exception(
                        "Writer failed for topic=%s partition=%s offset=%s. "
                        "Leaving the record uncommitted and exiting because %s is reserved but not implemented yet.",
                        record.topic,
                        record.partition,
                        record.offset,
                        AUDIO_DLQ,
                    )
                    raise

                record_logger.bind(
                    metric_name="write_ms",
                    metric_value=outcome.write_ms,
                ).info(
                    "Persisted writer outputs topic=%s rows=%s write_ms=%.3f",
                    record.topic,
                    outcome.rows_written,
                    outcome.write_ms,
                )
            service_logger.info("Writer shutdown requested. Closing Kafka consumer and database pool.")
        finally:
            restore_handlers()
            if pool is not None:
                close_database_pool(pool)
            consumer.close()

    def _persist_record(
        self,
        record: ConsumedRecord,
        *,
        pool: ConnectionPool | None = None,
        raw_envelope: dict[str, object] | None = None,
        write_started_at: float | None = None,
    ) -> WriterPersistenceOutcome:
        envelope = raw_envelope if raw_envelope is not None else deserialize_envelope(record.value)
        started_at = perf_counter() if write_started_at is None else write_started_at
        try:
            payload = validate_envelope_dict(envelope, expected_event_type=record.topic)
        except ValueError as exc:
            raise WriterStageError(
                "envelope_invalid",
                "Writer failed while validating the current envelope.",
            ) from exc
        context = self._extract_record_context(envelope)
        try:
            payload_model = coerce_payload_model(record.topic, payload)
        except WriterPayloadValidationError as exc:
            raise WriterStageError(
                "envelope_invalid",
                "Writer failed while validating the current payload.",
            ) from exc
        cursor_context: AbstractContextManager[tuple[object, object]]
        if pool is None:
            cursor_context = transaction_cursor(self.settings.database)
        else:
            cursor_context = pooled_transaction_cursor(pool)

        with cursor_context as (_, cursor):
            rows_written = persist_envelope_payload(
                cursor=cursor,
                topic=record.topic,
                payload=payload_model,
            )
            checkpoint_record = build_checkpoint_record(
                consumer_group=self.settings.consumer_group,
                topic_name=record.topic,
                partition_id=record.partition,
                run_id=str(envelope["run_id"]),
                last_committed_offset=record.offset,
            )
            checkpoint_rows = persist_checkpoint(cursor, checkpoint_record)
            decision = build_commit_decision(
                rows_written=rows_written,
                checkpoints_ready=checkpoint_rows > 0,
            )
            if not decision.commit_allowed:
                raise WriterStageError(
                    decision.failure_class or "invalid_persistence_result",
                    decision.reason,
                )
            write_elapsed_ms = (perf_counter() - started_at) * 1000.0
            run_id = context.run_id or str(envelope["run_id"])
            persist_system_metrics(
                cursor,
                build_writer_metric_payload(
                    run_id=run_id,
                    topic=record.topic,
                    metric_name="write_ms",
                    metric_value=write_elapsed_ms,
                    unit="ms",
                    status="ok",
                    partition=record.partition,
                    offset=record.offset,
                ),
            )
            persist_system_metrics(
                cursor,
                build_writer_metric_payload(
                    run_id=run_id,
                    topic=record.topic,
                    metric_name="rows_upserted",
                    metric_value=float(rows_written),
                    unit="count",
                    status="ok",
                    partition=record.partition,
                    offset=record.offset,
                ),
            )

        return WriterPersistenceOutcome(
            rows_written=rows_written,
            checkpoint_rows=checkpoint_rows,
            context=context,
            write_ms=write_elapsed_ms,
        )


def classify_writer_failure(error: Exception) -> WriterFailureDecision:
    """Return a stable writer failure class for one terminal error."""

    if isinstance(error, WriterStageError):
        return WriterFailureDecision(failure_class=error.failure_class)
    if isinstance(error, AudioFeaturesNaturalKeyError):
        return WriterFailureDecision(failure_class="feature_natural_key_conflict")
    return WriterFailureDecision(failure_class="writer_persistence_failed")
