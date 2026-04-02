from __future__ import annotations

import csv
import numpy as np
from pathlib import Path
import tempfile
from typing import Callable

import polars as pl
import pytest

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.modules.metrics import IngestionRunMetrics
from event_driven_audio_analytics.ingestion.modules.artifact_writer import write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_MISSING_FILE,
    VALIDATION_STATUS_PROBE_FAILED,
    VALIDATION_STATUS_SILENT,
    VALIDATION_STATUS_TOO_SHORT,
    VALIDATION_STATUS_VALIDATED,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import (
    MetadataRecord,
    load_small_subset_metadata,
)
from event_driven_audio_analytics.ingestion.modules.segmenter import AudioSegment, segment_audio
from event_driven_audio_analytics.ingestion.pipeline import IngestionPipeline
from event_driven_audio_analytics.shared.kafka import (
    KafkaDeliveryError,
    deserialize_envelope,
    producer_config,
)
from event_driven_audio_analytics.shared.models.envelope import validate_envelope_dict
from event_driven_audio_analytics.shared.settings import BaseServiceSettings


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


class _DeliveredMessage:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def topic(self) -> str:
        return self._topic


class RecordingProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: Callable[[object, object | None], None] | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key.decode("utf-8") if key is not None else None,
                "value": deserialize_envelope(value),
            }
        )
        if on_delivery is not None:
            on_delivery(None, _DeliveredMessage(topic))

    def poll(self, timeout: float = 0.0) -> int:
        return 0

    def flush(self, timeout: float | None = None) -> int:
        return 0


class UndeliveredProducer(RecordingProducer):
    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: Callable[[object, object | None], None] | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key.decode("utf-8") if key is not None else None,
                "value": deserialize_envelope(value),
            }
        )

    def flush(self, timeout: float | None = None) -> int:
        return 1


class DeliveryErrorProducer(RecordingProducer):
    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: Callable[[object, object | None], None] | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key.decode("utf-8") if key is not None else None,
                "value": deserialize_envelope(value),
            }
        )
        if on_delivery is not None:
            on_delivery(RuntimeError("broker unavailable"), None)


def _metadata_record_for_fixture(name: str) -> MetadataRecord:
    path = (FIXTURES_DIR / name).resolve()
    return MetadataRecord(
        track_id=2,
        artist_id=1,
        genre_label="Hip-Hop",
        subset="small",
        source_path=path.name,
        source_audio_uri=path.as_posix(),
    )


def _write_sample_tracks_csv(path: Path) -> None:
    rows = [
        ["", "artist", "set", "track"],
        ["", "id", "subset", "genre_top"],
        ["track_id", "", "", ""],
        ["2", "1", "small", "Hip-Hop"],
        ["3", "1", "medium", "Hip-Hop"],
        ["10", "6", "small", "Pop"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def test_metadata_etl_flattens_headers_and_filters_small_subset() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "tracks.csv"
        _write_sample_tracks_csv(csv_path)

        records = load_small_subset_metadata(
            str(csv_path),
            audio_root_path="/dataset/fma_small",
            subset="small",
        )

        assert [record.track_id for record in records] == [2, 10]
        assert records[0].artist_id == 1
        assert records[0].genre_label == "Hip-Hop"
        assert records[0].source_path == "000/000002.mp3"
        assert records[0].source_audio_uri == "/dataset/fma_small/000/000002.mp3"


def test_metadata_etl_supports_allowlist_and_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "tracks.csv"
        _write_sample_tracks_csv(csv_path)

        records = load_small_subset_metadata(
            str(csv_path),
            audio_root_path="/dataset/fma_small",
            subset="small",
            track_id_allowlist=(10, 999),
            max_tracks=1,
        )

        assert len(records) == 1
        assert records[0].track_id == 10


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("valid_synthetic_stereo_44k1.mp3", VALIDATION_STATUS_VALIDATED),
        ("silent_mono_32k.wav", VALIDATION_STATUS_SILENT),
        ("short_tone_mono_32k.wav", VALIDATION_STATUS_TOO_SHORT),
        ("corrupt_audio.mp3", VALIDATION_STATUS_PROBE_FAILED),
    ],
)
def test_audio_validation_outcomes(
    fixture_name: str,
    expected_status: str,
) -> None:
    result = validate_audio_record(
        _metadata_record_for_fixture(fixture_name),
        target_sample_rate_hz=32000,
    )

    assert result.validation_status == expected_status


def test_validation_reports_missing_file() -> None:
    record = MetadataRecord(
        track_id=2,
        artist_id=1,
        genre_label="Hip-Hop",
        subset="small",
        source_path="000/000002.mp3",
        source_audio_uri=(FIXTURES_DIR / "does_not_exist.mp3").as_posix(),
    )

    result = validate_audio_record(record, target_sample_rate_hz=32000)

    assert result.validation_status == VALIDATION_STATUS_MISSING_FILE


def test_decode_resample_outputs_mono_32k_waveform() -> None:
    result = validate_audio_record(
        _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
        target_sample_rate_hz=32000,
    )

    assert result.validation_status == VALIDATION_STATUS_VALIDATED
    assert result.source_sample_rate_hz == 44100
    assert result.decoded_audio is not None
    assert result.decoded_audio.sample_rate_hz == 32000
    assert result.decoded_audio.waveform.shape[0] == 1


def test_segment_count_matches_legacy_fixture_expectation() -> None:
    result = validate_audio_record(
        _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
        target_sample_rate_hz=32000,
    )
    assert result.decoded_audio is not None

    segments = segment_audio(
        run_id="demo-run",
        track_id=2,
        waveform=result.decoded_audio.waveform,
        sample_rate_hz=result.decoded_audio.sample_rate_hz,
    )

    assert len(segments) == 3
    assert segments[-1].is_last_segment is True


def test_segment_count_matches_30s_and_tail_padding_rules() -> None:
    waveform_29_95s = np.zeros((1, int(32000 * 29.95)), dtype=np.float32)
    waveform_30_6s = np.zeros((1, int(32000 * 30.6)), dtype=np.float32)

    segments_29_95s = segment_audio(
        run_id="demo-run",
        track_id=2,
        waveform=waveform_29_95s,
        sample_rate_hz=32000,
    )
    segments_30_6s = segment_audio(
        run_id="demo-run",
        track_id=666,
        waveform=waveform_30_6s,
        sample_rate_hz=32000,
    )

    assert len(segments_29_95s) == 19
    assert len(segments_30_6s) == 20


def test_artifact_writer_creates_wavs_checksums_and_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        samples = np.zeros((1, 32000 * 3), dtype=np.float32)
        segments = [
            AudioSegment(
                run_id="demo-run",
                track_id=2,
                segment_idx=0,
                waveform=samples,
                sample_rate=32000,
                duration_s=3.0,
                is_last_segment=True,
            )
        ]

        descriptors = write_segment_artifacts(Path(tmp_dir), segments)

        assert len(descriptors) == 1
        descriptor = descriptors[0]
        assert Path(descriptor.artifact_uri).exists()
        assert descriptor.checksum.startswith("sha256:")
        assert Path(descriptor.manifest_uri).exists()

        manifest = pl.read_parquet(descriptor.manifest_uri)
        assert manifest.shape == (1, 9)
        assert manifest["artifact_uri"][0] == descriptor.artifact_uri


def test_pipeline_emits_metadata_before_segment_ready_and_writes_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = IngestionSettings(
            base=BaseServiceSettings(
                service_name="ingestion",
                run_id="demo-run",
                kafka_bootstrap_servers="unused:9092",
                artifacts_root=Path(tmp_dir),
            ),
            metadata_csv_path="unused.csv",
            audio_root_path="unused",
            subset="small",
            target_sample_rate_hz=32000,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            track_id_allowlist=(),
            max_tracks=1,
            producer_retries=10,
            producer_retry_backoff_ms=250,
            producer_retry_backoff_max_ms=5000,
            producer_delivery_timeout_ms=120000,
        )
        pipeline = IngestionPipeline(settings=settings)
        producer = RecordingProducer()

        result = pipeline.process_record(
            producer,
            _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
        )

        assert result.validation.validation_status == VALIDATION_STATUS_VALIDATED
        assert len(result.segment_descriptors) == 3
        assert [message["topic"] for message in producer.messages] == [
            "audio.metadata",
            "audio.segment.ready",
            "audio.segment.ready",
            "audio.segment.ready",
        ]
        assert [message["key"] for message in producer.messages] == [
            "2",
            "2",
            "2",
            "2",
        ]

        metadata_envelope = producer.messages[0]["value"]
        assert isinstance(metadata_envelope, dict)
        validate_envelope_dict(metadata_envelope, expected_event_type="audio.metadata")

        for message in producer.messages[1:]:
            envelope = message["value"]
            assert isinstance(envelope, dict)
            validate_envelope_dict(envelope, expected_event_type="audio.segment.ready")
            assert Path(str(envelope["payload"]["artifact_uri"])).exists()


def test_pipeline_run_publishes_run_level_system_metrics() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = IngestionSettings(
            base=BaseServiceSettings(
                service_name="ingestion",
                run_id="demo-run",
                kafka_bootstrap_servers="unused:9092",
                artifacts_root=Path(tmp_dir),
            ),
            metadata_csv_path="unused.csv",
            audio_root_path="unused",
            subset="small",
            target_sample_rate_hz=32000,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            track_id_allowlist=(),
            max_tracks=2,
            producer_retries=10,
            producer_retry_backoff_ms=250,
            producer_retry_backoff_max_ms=5000,
            producer_delivery_timeout_ms=120000,
        )
        
        class StubbedPipeline(IngestionPipeline):
            def load_metadata_records(self) -> list[MetadataRecord]:
                return [
                    _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
                    _metadata_record_for_fixture("corrupt_audio.mp3"),
                ]

        pipeline = StubbedPipeline(settings=settings)
        producer = RecordingProducer()

        pipeline.run(producer=producer)

        metric_messages = [message for message in producer.messages if message["topic"] == "system.metrics"]
        assert [message["key"] for message in metric_messages] == [
            "ingestion",
            "ingestion",
            "ingestion",
            "ingestion",
        ]
        assert [message["value"]["payload"]["metric_name"] for message in metric_messages] == [
            "tracks_total",
            "segments_total",
            "validation_failures",
            "artifact_write_ms",
        ]
        assert [message["value"]["payload"]["metric_value"] for message in metric_messages[:3]] == [
            2.0,
            3.0,
            1.0,
        ]
        assert metric_messages[3]["value"]["payload"]["unit"] == "ms"


def test_ingestion_run_metrics_render_expected_payloads() -> None:
    metrics = IngestionRunMetrics()
    metrics.record_track(segment_count=3, validation_failed=False, artifact_write_ms=12.5)
    metrics.record_track(segment_count=0, validation_failed=True, artifact_write_ms=0.0)

    payloads = metrics.as_payloads(run_id="demo-run", service_name="ingestion")

    assert [payload.metric_name for payload in payloads] == [
        "tracks_total",
        "segments_total",
        "validation_failures",
        "artifact_write_ms",
    ]
    assert [payload.metric_value for payload in payloads] == [2.0, 3.0, 1.0, 12.5]
    assert payloads[-1].unit == "ms"


def test_producer_config_sets_idempotence_and_retry_backoff_defaults() -> None:
    config = producer_config(
        bootstrap_servers="kafka:29092",
        client_id="ingestion-producer",
    )

    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["retries"] == 10
    assert config["retry.backoff.ms"] == 250
    assert config["retry.backoff.max.ms"] == 5000
    assert config["delivery.timeout.ms"] == 120000


def test_process_record_raises_when_kafka_delivery_times_out() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = IngestionSettings(
            base=BaseServiceSettings(
                service_name="ingestion",
                run_id="demo-run",
                kafka_bootstrap_servers="unused:9092",
                artifacts_root=Path(tmp_dir),
            ),
            metadata_csv_path="unused.csv",
            audio_root_path="unused",
            subset="small",
            target_sample_rate_hz=32000,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            track_id_allowlist=(),
            max_tracks=1,
            producer_retries=10,
            producer_retry_backoff_ms=250,
            producer_retry_backoff_max_ms=5000,
            producer_delivery_timeout_ms=100,
        )
        pipeline = IngestionPipeline(settings=settings)

        with pytest.raises(KafkaDeliveryError, match="timed out waiting for delivery report"):
            pipeline.process_record(
                UndeliveredProducer(),
                _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
            )


def test_process_record_raises_when_kafka_delivery_reports_error() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = IngestionSettings(
            base=BaseServiceSettings(
                service_name="ingestion",
                run_id="demo-run",
                kafka_bootstrap_servers="unused:9092",
                artifacts_root=Path(tmp_dir),
            ),
            metadata_csv_path="unused.csv",
            audio_root_path="unused",
            subset="small",
            target_sample_rate_hz=32000,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            track_id_allowlist=(),
            max_tracks=1,
            producer_retries=10,
            producer_retry_backoff_ms=250,
            producer_retry_backoff_max_ms=5000,
            producer_delivery_timeout_ms=120000,
        )
        pipeline = IngestionPipeline(settings=settings)

        with pytest.raises(KafkaDeliveryError, match="broker unavailable"):
            pipeline.process_record(
                DeliveryErrorProducer(),
                _metadata_record_for_fixture("valid_synthetic_stereo_44k1.mp3"),
            )
