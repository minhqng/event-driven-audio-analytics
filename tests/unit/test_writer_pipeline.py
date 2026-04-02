from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, DatabaseSettings
from event_driven_audio_analytics.writer.config import WriterSettings
from event_driven_audio_analytics.writer.modules.consumer import ConsumedRecord
from event_driven_audio_analytics.writer.pipeline import WriterPipeline


class FakeConsumer:
    def __init__(self) -> None:
        self.commit_calls: list[tuple[object, bool]] = []
        self.closed = False

    def commit(self, *, message: object, asynchronous: bool) -> None:
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
        )

    def build_record(self) -> ConsumedRecord:
        return ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=b"{}",
            message=object(),
        )

    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_failed_record_is_left_uncommitted(
        self,
        poll_record: object,
        build_writer_consumer: object,
    ) -> None:
        consumer = FakeConsumer()
        build_writer_consumer.return_value = consumer
        poll_record.side_effect = [self.build_record(), KeyboardInterrupt()]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(pipeline, "_persist_record", side_effect=ValueError("boom")):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run()

        self.assertEqual(consumer.commit_calls, [])
        self.assertTrue(consumer.closed)

    @patch("event_driven_audio_analytics.writer.pipeline.build_writer_consumer")
    @patch("event_driven_audio_analytics.writer.pipeline.poll_record")
    def test_successful_record_is_committed(
        self,
        poll_record: object,
        build_writer_consumer: object,
    ) -> None:
        consumer = FakeConsumer()
        build_writer_consumer.return_value = consumer
        record = self.build_record()
        poll_record.side_effect = [record, KeyboardInterrupt()]
        pipeline = WriterPipeline(settings=self.build_settings())

        with patch.object(pipeline, "_persist_record", return_value=(1, True)):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run()

        self.assertEqual(consumer.commit_calls, [(record.message, False)])
        self.assertTrue(consumer.closed)


if __name__ == "__main__":
    unittest.main()
