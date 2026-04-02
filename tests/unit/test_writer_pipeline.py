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

        with patch.object(WriterPipeline, "_persist_record", side_effect=ValueError("boom")):
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

        with patch.object(WriterPipeline, "_persist_record", return_value=(1, True)):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run()

        self.assertEqual(consumer.commit_calls, [(record.message, False)])
        self.assertTrue(consumer.closed)

    @patch("event_driven_audio_analytics.writer.pipeline.persist_checkpoint")
    @patch("event_driven_audio_analytics.writer.pipeline.persist_envelope_payload")
    @patch("event_driven_audio_analytics.writer.pipeline.transaction_cursor")
    def test_persist_record_accepts_canonical_v1_envelope(
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

        self.assertEqual(result, (1, True))
        persist_envelope_payload.assert_called_once_with(
            cursor=unittest.mock.ANY,
            topic="audio.features",
            payload_data=envelope["payload"],
        )
        self.assertEqual(
            persist_checkpoint.call_args.args[1]["run_id"],
            "demo-run",
        )

    def test_persist_record_rejects_run_id_mismatch(self) -> None:
        pipeline = WriterPipeline(settings=self.build_settings())
        envelope = self.build_features_envelope()
        envelope["run_id"] = "other-run"
        record = ConsumedRecord(
            topic="audio.features",
            partition=0,
            offset=12,
            value=serialize_envelope(envelope),
            message=object(),
        )

        with self.assertRaisesRegex(ValueError, "run_id"):
            pipeline._persist_record(record)


if __name__ == "__main__":
    unittest.main()
