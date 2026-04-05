from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.kafka import serialize_envelope
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.envelope import build_envelope
from event_driven_audio_analytics.shared.logging import ServiceLoggerAdapter
from event_driven_audio_analytics.shared.settings import BaseServiceSettings, DatabaseSettings
from event_driven_audio_analytics.writer.config import WriterSettings
from event_driven_audio_analytics.writer.modules.consumer import ConsumedRecord
from event_driven_audio_analytics.writer.pipeline import (
    WriterPersistenceOutcome,
    WriterPipeline,
    WriterRecordContext,
    classify_writer_failure,
    WriterStageError,
)
from event_driven_audio_analytics.writer.modules.upsert_features import AudioFeaturesNaturalKeyError


class FakeConsumer:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.commit_calls: list[tuple[object, bool]] = []
        self.closed = False
        self.fail_commit = fail_commit
        self.commit_attempts = 0

    def commit(self, *, message: object, asynchronous: bool) -> None:
        self.commit_attempts += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commit_calls.append((message, asynchronous))

    def close(self) -> None:
        self.closed = True


class WriterPipelineTests(unittest.TestCase):
    def build_settings(self) -> WriterSettings:
        return WriterSettings(
            base=BaseServiceSettings(
                service_name="writer",
                run_id="demo-run",
                kafka_bootstrap_servers="kafka:29092",
                artifacts_root=Path("/app/artifacts"),
            ),
            database=DatabaseSettings(
                host="timescaledb",
                port=5432,
                database="audio_analytics",
                user="audio_analytics",
                password="audio_analytics",
            ),
            consumer_group="event-driven-audio-analytics-writer",
            auto_offset_reset="earliest",
            poll_timeout_s=1.0,
            session_timeout_ms=45000,
            max_poll_interval_ms=300000,
            consumer_retry_backoff_ms=250,
            consumer_retry_backoff_max_ms=5000,
            db_pool_min_size=1,
            db_pool_max_size=4,
            db_pool_timeout_s=30.0,
        )

    def build_record(self) -> ConsumedRecord:
        return ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=serialize_envelope(self.build_features_envelope()),
            message=object(),
        )

    def build_features_envelope(self) -> dict[str, object]:
        payload = AudioFeaturesPayload(
            ts="2026-04-02T00:00:10Z",
            run_id="demo-run",
            track_id=2,
            segment_idx=0,
            artifact_uri="/artifacts/runs/demo-run/segments/2/0.wav",
            checksum="sha256:segment-000",
            rms=0.42,
            silent_flag=False,
            mel_bins=128,
            mel_frames=300,
            processing_ms=12.5,
            manifest_uri="/artifacts/runs/demo-run/manifests/segments.parquet",
        )
        return build_envelope(
            "audio.features",
            "processing",
            payload,
            event_id="evt-features-001",
            produced_at="2026-04-02T00:00:11Z",
        ).to_dict()

    def build_outcome(self) -> WriterPersistenceOutcome:
        return WriterPersistenceOutcome(
            rows_written=1,
            checkpoint_rows=1,
            context=WriterRecordContext(
                run_id="demo-run",
                trace_id="run/demo-run/track/2",
                track_id=2,
                segment_idx=0,
            ),
            write_ms=9.5,
        )

    def build_logger(self) -> ServiceLoggerAdapter:
        import logging

        logger = logging.getLogger("writer-test")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        return ServiceLoggerAdapter(
            logger,
            {
                "service_name": "writer",
                "run_id": "demo-run",
            },
        )

    @patch("event_driven_audio_analytics.writer.pipeline.close_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.open_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_failed_record_is_left_uncommitted_and_exits(
        self,
        poll_record: object,
        build_writer_consumer: object,
        open_database_pool: object,
        close_database_pool: object,
    ) -> None:
        consumer = FakeConsumer()
        build_writer_consumer.return_value = consumer
        open_database_pool.return_value = object()
        poll_record.side_effect = [self.build_record()]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(
            WriterPipeline,
            "_persist_record",
            side_effect=WriterStageError("writer_persistence_failed", "boom"),
        ), patch.object(WriterPipeline, "_emit_failure_metric") as emit_failure_metric:
            with self.assertRaises(WriterStageError):
                pipeline.run(logger=self.build_logger())

        self.assertEqual(consumer.commit_calls, [])
        self.assertTrue(emit_failure_metric.called)
        self.assertTrue(consumer.closed)
        close_database_pool.assert_called_once()

    @patch("event_driven_audio_analytics.writer.pipeline.close_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.open_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_successful_record_is_committed_once(
        self,
        poll_record: object,
        build_writer_consumer: object,
        open_database_pool: object,
        close_database_pool: object,
    ) -> None:
        consumer = FakeConsumer()
        build_writer_consumer.return_value = consumer
        open_database_pool.return_value = object()
        record = self.build_record()
        poll_record.side_effect = [record, KeyboardInterrupt()]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(
            WriterPipeline,
            "_persist_record",
            return_value=self.build_outcome(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run(logger=self.build_logger())

        self.assertEqual(consumer.commit_calls, [(record.message, False)])
        self.assertTrue(consumer.closed)
        close_database_pool.assert_called_once()

    @patch("event_driven_audio_analytics.writer.pipeline.close_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.open_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_commit_failure_emits_failure_metric_and_stops_before_next_record(
        self,
        poll_record: object,
        build_writer_consumer: object,
        open_database_pool: object,
        close_database_pool: object,
    ) -> None:
        consumer = FakeConsumer(fail_commit=True)
        build_writer_consumer.return_value = consumer
        open_database_pool.return_value = object()
        first_record = self.build_record()
        second_record = self.build_record()
        second_record.offset = 13
        poll_record.side_effect = [first_record, second_record]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(
            WriterPipeline,
            "_persist_record",
            return_value=self.build_outcome(),
        ), patch.object(WriterPipeline, "_emit_failure_metric") as emit_failure_metric:
            with self.assertRaises(WriterStageError) as exc_info:
                pipeline.run(logger=self.build_logger())

        self.assertEqual(exc_info.exception.failure_class, "offset_commit_failed")
        self.assertEqual(consumer.commit_calls, [])
        self.assertEqual(consumer.commit_attempts, 1)
        self.assertEqual(poll_record.call_count, 1)
        emit_failure_metric.assert_called_once()
        self.assertTrue(consumer.closed)
        close_database_pool.assert_called_once()

    @patch("event_driven_audio_analytics.writer.pipeline.persist_checkpoint")
    @patch("event_driven_audio_analytics.writer.pipeline.persist_system_metrics")
    @patch("event_driven_audio_analytics.writer.pipeline.persist_envelope_payload")
    @patch("event_driven_audio_analytics.writer.pipeline.transaction_cursor")
    def test_persist_record_accepts_canonical_v1_envelope(
        self,
        transaction_cursor: object,
        persist_envelope_payload: object,
        persist_system_metrics: object,
        persist_checkpoint: object,
    ) -> None:
        @contextmanager
        def fake_transaction_cursor(_: object):
            yield (object(), object())

        transaction_cursor.side_effect = fake_transaction_cursor
        persist_envelope_payload.return_value = 1
        persist_checkpoint.return_value = 1
        pipeline = WriterPipeline(settings=self.build_settings())
        envelope = self.build_features_envelope()
        record = ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=serialize_envelope(envelope),
            message=object(),
        )

        result = pipeline._persist_record(record)

        self.assertEqual(result.rows_written, 1)
        self.assertEqual(result.checkpoint_rows, 1)
        self.assertEqual(result.context.run_id, "demo-run")
        self.assertEqual(result.context.track_id, 2)
        self.assertGreaterEqual(result.write_ms, 0.0)
        persist_envelope_payload.assert_called_once_with(
            cursor=unittest.mock.ANY,
            topic="audio.features",
            payload=unittest.mock.ANY,
        )
        persisted_payload = persist_envelope_payload.call_args.kwargs["payload"]
        self.assertIsInstance(persisted_payload, AudioFeaturesPayload)
        self.assertEqual(persisted_payload.processing_ms, 12.5)
        self.assertEqual(
            persist_checkpoint.call_args.args[1]["run_id"],
            "demo-run",
        )
        self.assertEqual(persist_system_metrics.call_count, 2)
        self.assertEqual(
            [call.args[1].metric_name for call in persist_system_metrics.call_args_list],
            ["write_ms", "rows_upserted"],
        )

    @patch("event_driven_audio_analytics.writer.pipeline.persist_checkpoint")
    @patch("event_driven_audio_analytics.writer.pipeline.persist_envelope_payload")
    @patch("event_driven_audio_analytics.writer.pipeline.transaction_cursor")
    def test_persist_record_rejects_invalid_checkpoint_result_before_commit(
        self,
        transaction_cursor: object,
        persist_envelope_payload: object,
        persist_checkpoint: object,
    ) -> None:
        @contextmanager
        def fake_transaction_cursor(_: object):
            yield (object(), object())

        transaction_cursor.side_effect = fake_transaction_cursor
        persist_envelope_payload.return_value = 1
        persist_checkpoint.return_value = 0
        pipeline = WriterPipeline(settings=self.build_settings())

        with self.assertRaises(WriterStageError) as exc_info:
            pipeline._persist_record(self.build_record())

        self.assertEqual(exc_info.exception.failure_class, "checkpoint_failed")

    def test_persist_record_rejects_top_level_payload_run_id_mismatch(self) -> None:
        pipeline = WriterPipeline(settings=self.build_settings())
        envelope = self.build_features_envelope()
        envelope["payload"]["run_id"] = "other-run"
        record = ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=serialize_envelope(envelope),
            message=object(),
        )

        with self.assertRaises(WriterStageError) as exc_info:
            pipeline._persist_record(record)

        self.assertEqual(exc_info.exception.failure_class, "envelope_invalid")

    def test_persist_record_rejects_payload_schema_drift(self) -> None:
        pipeline = WriterPipeline(settings=self.build_settings())
        envelope = self.build_features_envelope()
        del envelope["payload"]["processing_ms"]
        record = ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=serialize_envelope(envelope),
            message=object(),
        )

        with self.assertRaises(WriterStageError) as exc_info:
            pipeline._persist_record(record)

        self.assertEqual(exc_info.exception.failure_class, "envelope_invalid")

    def test_classify_writer_failure_distinguishes_feature_key_conflicts(self) -> None:
        decision = classify_writer_failure(
            AudioFeaturesNaturalKeyError("duplicate natural-key rows"),
        )

        self.assertEqual(decision.failure_class, "feature_natural_key_conflict")

    def test_classify_writer_failure_keeps_generic_value_errors_out_of_envelope_bucket(self) -> None:
        decision = classify_writer_failure(ValueError("unexpected sink-side value error"))

        self.assertEqual(decision.failure_class, "writer_persistence_failed")

    @patch("event_driven_audio_analytics.writer.pipeline.close_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.open_database_pool")
    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_invalid_json_is_classified_as_envelope_invalid(
        self,
        poll_record: object,
        build_writer_consumer: object,
        open_database_pool: object,
        close_database_pool: object,
    ) -> None:
        consumer = FakeConsumer()
        build_writer_consumer.return_value = consumer
        open_database_pool.return_value = object()
        poll_record.side_effect = [
            ConsumedRecord(
                topic="audio.features",
                partition=0,
                offset=12,
                value=b"{not-json",
                message=object(),
            )
        ]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(WriterPipeline, "_emit_failure_metric") as emit_failure_metric:
            with self.assertRaises(WriterStageError) as exc_info:
                pipeline.run(logger=self.build_logger())

        self.assertEqual(exc_info.exception.failure_class, "envelope_invalid")
        self.assertEqual(consumer.commit_calls, [])
        emit_failure_metric.assert_called_once()
        self.assertTrue(consumer.closed)
        close_database_pool.assert_called_once()


if __name__ == "__main__":
    unittest.main()
