from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import tempfile

import pytest

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord
from event_driven_audio_analytics.ingestion.modules.runtime import (
    IngestionReadinessError,
    check_runtime_dependencies,
)
from event_driven_audio_analytics.ingestion.pipeline import IngestionPipeline
from event_driven_audio_analytics.shared.logging import JsonLogFormatter, ServiceLoggerAdapter
from event_driven_audio_analytics.shared.settings import BaseServiceSettings


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
SMOKE_METADATA_CSV = FIXTURES_DIR / "smoke_tracks.csv"
SMOKE_AUDIO_ROOT = FIXTURES_DIR / "smoke_fma_small"


class RecordingProducer:
    def produce(self, **kwargs: object) -> None:
        on_delivery = kwargs.get("on_delivery")
        if callable(on_delivery):
            on_delivery(None, None)

    def poll(self, timeout: float = 0.0) -> int:
        return 0

    def flush(self, timeout: float | None = None) -> int:
        return 0


def _ingestion_settings(
    artifacts_root: str | Path,
    metadata_csv_path: str | Path,
    audio_root_path: str | Path,
    *,
    track_id_allowlist: tuple[int, ...] = (2, 666),
) -> IngestionSettings:
    return IngestionSettings(
        base=BaseServiceSettings(
            service_name="ingestion",
            run_id="demo-run",
            kafka_bootstrap_servers="unused:9092",
            artifacts_root=Path(artifacts_root),
        ),
        metadata_csv_path=str(metadata_csv_path),
        audio_root_path=str(audio_root_path),
        subset="small",
            target_sample_rate_hz=32000,
            segment_duration_s=3.0,
            segment_overlap_s=1.5,
            min_duration_s=1.0,
            silence_threshold_db=-60.0,
            track_id_allowlist=track_id_allowlist,
            max_tracks=1,
            producer_retries=10,
            producer_retry_backoff_ms=250,
            producer_retry_backoff_max_ms=5000,
            producer_delivery_timeout_ms=120000,
        startup_timeout_s=0.1,
        startup_retry_interval_s=0.01,
    )


def _metadata_record(track_id: int, fixture_name: str) -> MetadataRecord:
    fixture_path = (FIXTURES_DIR / fixture_name).resolve()
    return MetadataRecord(
        track_id=track_id,
        artist_id=1,
        genre_label="Experimental",
        subset="small",
        source_path=fixture_path.name,
        source_audio_uri=fixture_path.as_posix(),
        declared_duration_s=30.60,
    )


def test_readiness_succeeds_when_kafka_topics_and_paths_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_fails_when_required_topic_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {"audio.metadata", "audio.segment.ready"},
        )

        with pytest.raises(IngestionReadinessError, match="system.metrics"):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_fails_when_metadata_csv_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        audio_root = Path(tmp_dir) / "audio"
        audio_root.mkdir()

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        with pytest.raises(IngestionReadinessError, match="METADATA_CSV_PATH"):
            check_runtime_dependencies(
                _ingestion_settings(artifacts_root, Path(tmp_dir) / "missing.csv", audio_root)
            )


def test_readiness_fails_when_audio_root_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        with pytest.raises(IngestionReadinessError, match="AUDIO_ROOT_PATH"):
            check_runtime_dependencies(
                _ingestion_settings(artifacts_root, metadata_csv, Path(tmp_dir) / "missing-audio")
            )


def test_readiness_fails_when_artifacts_root_is_not_writable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )
        original_access = __import__(
            "event_driven_audio_analytics.ingestion.modules.runtime",
            fromlist=["access"],
        ).access

        def fake_access(path: object, mode: int) -> bool:
            if Path(path) == artifacts_root and mode & 0o2:
                return False
            return original_access(path, mode)

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime.access",
            fake_access,
        )

        with pytest.raises(IngestionReadinessError, match="ARTIFACTS_ROOT"):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_creates_run_scoped_artifact_directories_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        settings = _ingestion_settings(artifacts_root, metadata_csv, audio_root)
        run_root_path = artifacts_root / "runs" / settings.base.run_id
        check_runtime_dependencies(settings)

        assert (run_root_path / "segments").is_dir()
        assert (run_root_path / "manifests").is_dir()
        assert (run_root_path / "segments" / "2").is_dir()
        assert not (run_root_path / "manifests" / "segments.parquet").exists()


@pytest.mark.parametrize("blocked_leaf", ["segments", "manifests"])
def test_readiness_fails_when_run_scoped_artifact_target_is_blocked_by_file(
    monkeypatch: pytest.MonkeyPatch,
    blocked_leaf: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        blocked_path = artifacts_root / "runs" / "demo-run" / blocked_leaf
        blocked_path.parent.mkdir(parents=True, exist_ok=True)
        blocked_path.write_text("blocked\n", encoding="utf-8")

        with pytest.raises(IngestionReadinessError, match=blocked_path.as_posix()):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_fails_when_track_segment_target_is_blocked_by_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        blocked_path = artifacts_root / "runs" / "demo-run" / "segments" / "2"
        blocked_path.parent.mkdir(parents=True, exist_ok=True)
        blocked_path.write_text("blocked\n", encoding="utf-8")

        with pytest.raises(IngestionReadinessError, match=blocked_path.as_posix()):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_ignores_allowlisted_track_ids_not_selected_by_metadata_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        ignored_path = artifacts_root / "runs" / "demo-run" / "segments" / "999"
        ignored_path.parent.mkdir(parents=True, exist_ok=True)
        ignored_path.write_text("blocked\n", encoding="utf-8")

        check_runtime_dependencies(
            _ingestion_settings(
                artifacts_root,
                metadata_csv,
                audio_root,
                track_id_allowlist=(2, 999),
            )
        )

        assert (artifacts_root / "runs" / "demo-run" / "segments" / "2").is_dir()
        assert ignored_path.is_file()


def test_readiness_fails_when_run_scoped_write_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        def fail_segments_probe(path: Path, *, label: str) -> None:
            if path.name == "segments":
                raise IngestionReadinessError(
                    f"{label} is not writable: {path.as_posix()} (probe failed)"
                )

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._probe_directory_write",
            fail_segments_probe,
        )

        with pytest.raises(IngestionReadinessError, match="ARTIFACT_SEGMENTS_DIR\\[demo-run\\]"):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_fails_when_manifest_target_is_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        manifest_path = artifacts_root / "runs" / "demo-run" / "manifests" / "segments.parquet"
        manifest_path.mkdir(parents=True, exist_ok=True)

        with pytest.raises(IngestionReadinessError, match=manifest_path.as_posix()):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_readiness_fails_when_manifest_target_is_not_writable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_root = Path(tmp_dir) / "artifacts"
        artifacts_root.mkdir()
        metadata_csv = SMOKE_METADATA_CSV
        audio_root = SMOKE_AUDIO_ROOT

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime._list_kafka_topics",
            lambda bootstrap_servers: {
                "audio.metadata",
                "audio.segment.ready",
                "system.metrics",
            },
        )

        manifest_path = artifacts_root / "runs" / "demo-run" / "manifests" / "segments.parquet"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("existing manifest\n", encoding="utf-8")

        original_access = __import__(
            "event_driven_audio_analytics.ingestion.modules.runtime",
            fromlist=["access"],
        ).access

        def fake_access(path: object, mode: int) -> bool:
            if Path(path) == manifest_path and mode & 0o2:
                return False
            return original_access(path, mode)

        monkeypatch.setattr(
            "event_driven_audio_analytics.ingestion.modules.runtime.access",
            fake_access,
        )

        with pytest.raises(IngestionReadinessError, match=manifest_path.as_posix()):
            check_runtime_dependencies(_ingestion_settings(artifacts_root, metadata_csv, audio_root))


def test_json_formatter_emits_trace_run_and_track_context() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())

    logger = logging.getLogger("test-ingestion-json")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    adapter = ServiceLoggerAdapter(
        logger,
        {
            "service_name": "ingestion",
            "run_id": "demo-run",
        },
    ).bind(
        trace_id="run/demo-run/track/2",
        track_id=2,
        topic="audio.metadata",
    )
    adapter.info("json smoke")

    payload = json.loads(stream.getvalue().strip())
    assert payload["run_id"] == "demo-run"
    assert payload["trace_id"] == "run/demo-run/track/2"
    assert payload["track_id"] == 2
    assert payload["topic"] == "audio.metadata"


def test_reject_path_log_records_include_validation_status(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipeline = IngestionPipeline(
            settings=_ingestion_settings(tmp_dir, SMOKE_METADATA_CSV, SMOKE_AUDIO_ROOT)
        )
        producer = RecordingProducer()
        caplog.set_level(logging.WARNING, logger="ingestion")

        result = pipeline.process_record(
            producer,
            _metadata_record(666, "corrupt_audio.mp3"),
        )

        assert result.validation.validation_status == "probe_failed"
        matching_record = next(
            record
            for record in caplog.records
            if "Published metadata only for rejected track" in record.getMessage()
        )
        assert matching_record.validation_status == "probe_failed"
        assert matching_record.track_id == 666
        assert matching_record.trace_id == "run/demo-run/track/666"


def test_unrecoverable_runtime_failure_logs_reserved_dlq_message_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class ExplodingPipeline(IngestionPipeline):
        def load_metadata_records(self) -> list[MetadataRecord]:
            return [_metadata_record(777, "valid_synthetic_stereo_44k1.mp3")]

        def process_record(self, producer: object, record: MetadataRecord) -> object:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "event_driven_audio_analytics.ingestion.pipeline.wait_for_runtime_dependencies",
        lambda settings, logger: None,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        pipeline = ExplodingPipeline(
            settings=_ingestion_settings(tmp_dir, SMOKE_METADATA_CSV, SMOKE_AUDIO_ROOT)
        )
        caplog.set_level(logging.ERROR, logger="ingestion")

        with pytest.raises(RuntimeError, match="boom"):
            pipeline.run(producer=object())

        matching_record = next(
            record
            for record in caplog.records
            if "audio.dlq is reserved and not published by this bounded PoC" in record.getMessage()
        )
        assert matching_record.failure_class == "unrecoverable"
        assert matching_record.track_id == 777
        assert matching_record.trace_id == "run/demo-run/track/777"


def test_final_runtime_failure_logs_reserved_dlq_message_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FlushPendingProducer(RecordingProducer):
        def flush(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(
        "event_driven_audio_analytics.ingestion.pipeline.wait_for_runtime_dependencies",
        lambda settings, logger: None,
    )
    monkeypatch.setattr(
        IngestionPipeline,
        "load_metadata_records",
        lambda self: [],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        pipeline = IngestionPipeline(
            settings=_ingestion_settings(tmp_dir, SMOKE_METADATA_CSV, SMOKE_AUDIO_ROOT)
        )
        caplog.set_level(logging.ERROR, logger="ingestion")

        with pytest.raises(RuntimeError, match="undelivered Kafka messages still queued"):
            pipeline.run(producer=FlushPendingProducer())

        matching_record = next(
            record
            for record in caplog.records
            if "audio.dlq is reserved and not published by this bounded PoC" in record.getMessage()
        )
        assert matching_record.failure_class == "unrecoverable"
        assert matching_record.topic == "system.metrics"
        assert matching_record.trace_id == "run/demo-run/service/ingestion"
        assert getattr(matching_record, "track_id", None) is None
