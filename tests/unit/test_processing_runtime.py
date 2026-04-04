from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import wave

import numpy as np
import pytest

from event_driven_audio_analytics.ingestion.modules.publisher import build_segment_ready_event
from event_driven_audio_analytics.processing.config import ProcessingSettings
from event_driven_audio_analytics.processing.modules.artifact_loader import ArtifactChecksumMismatch
from event_driven_audio_analytics.processing.modules.runtime import (
    ProcessingReadinessError,
    check_runtime_dependencies,
)
from event_driven_audio_analytics.processing.pipeline import (
    ProcessingPipeline,
    ProcessingStageError,
    classify_processing_failure,
)
from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.kafka import deserialize_envelope, serialize_envelope
from event_driven_audio_analytics.shared.logging import JsonLogFormatter, ServiceLoggerAdapter
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.settings import BaseServiceSettings


class RecordingProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: object | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key.decode("utf-8") if key is not None else None,
                "value": deserialize_envelope(value),
            }
        )
        if on_delivery is not None:
            on_delivery(None, None)

    def flush(self, timeout: float | None = None) -> int:
        return 0

    def poll(self, timeout: float = 0.0) -> int:
        return 0


class FakeMessage:
    def __init__(self, *, topic: str, partition: int, offset: int, value: bytes) -> None:
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._value = value

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset

    def value(self) -> bytes:
        return self._value

    def error(self) -> None:
        return None

    def key(self) -> None:
        return None


class FakeConsumer:
    def __init__(self, poll_results: list[object]) -> None:
        self._poll_results = list(poll_results)
        self.commit_calls: list[FakeMessage] = []
        self.close_calls = 0
        self.poll_calls = 0

    def poll(self, timeout: float = 0.0) -> object:
        self.poll_calls += 1
        if not self._poll_results:
            return None
        next_result = self._poll_results.pop(0)
        if isinstance(next_result, BaseException):
            raise next_result
        return next_result

    def commit(self, *, message: FakeMessage, asynchronous: bool) -> None:
        self.commit_calls.append(message)

    def close(self) -> None:
        self.close_calls += 1


class CommitFailingConsumer(FakeConsumer):
    def commit(self, *, message: FakeMessage, asynchronous: bool) -> None:
        raise RuntimeError("commit failed")


def _processing_settings(artifacts_root: Path) -> ProcessingSettings:
    return ProcessingSettings(
        base=BaseServiceSettings(
            service_name="processing",
            run_id="demo-run",
            kafka_bootstrap_servers="unused:9092",
            artifacts_root=artifacts_root,
        ),
        consumer_group="event-driven-audio-analytics-processing",
        auto_offset_reset="earliest",
        poll_timeout_s=1.0,
        session_timeout_ms=45000,
        max_poll_interval_ms=300000,
        consumer_retry_backoff_ms=250,
        consumer_retry_backoff_max_ms=5000,
        artifact_retry_attempts=3,
        artifact_retry_backoff_ms=250,
        artifact_retry_backoff_max_ms=5000,
        target_sample_rate_hz=32000,
        n_mels=128,
        n_fft=1024,
        hop_length=320,
        f_min=0,
        f_max=16000,
        target_frames=300,
        silence_threshold_db=-60.0,
        segment_silence_floor=1e-7,
        log_epsilon=1e-9,
        producer_retries=10,
        producer_retry_backoff_ms=250,
        producer_retry_backoff_max_ms=5000,
        producer_delivery_timeout_ms=120000,
    )


def _write_tone_wav(
    path: Path,
    *,
    duration_s: float = 3.0,
    sample_rate_hz: int = 32000,
    amplitude: float = 0.2,
    frequency_hz: float = 440.0,
) -> None:
    sample_count = int(round(duration_s * sample_rate_hz))
    timeline = np.arange(sample_count, dtype=np.float64) / float(sample_rate_hz)
    waveform = amplitude * np.sin(2.0 * np.pi * frequency_hz * timeline)
    pcm = np.round(np.clip(waveform, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(pcm.tobytes())


def _build_segment_ready_bytes(tmp_path: Path) -> bytes:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path)
    payload = AudioSegmentReadyPayload(
        run_id="demo-run",
        track_id=2,
        segment_idx=0,
        artifact_uri=artifact_path.as_posix(),
        checksum=sha256_file(artifact_path),
        sample_rate=32000,
        duration_s=3.0,
        is_last_segment=True,
    )
    return serialize_envelope(build_segment_ready_event(payload).to_dict())


def _service_logger() -> ServiceLoggerAdapter:
    logger = logging.getLogger("processing-runtime-test")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return ServiceLoggerAdapter(
        logger,
        {
            "service_name": "processing",
            "run_id": "demo-run",
        },
    )


def test_processing_settings_from_env_prefers_kafka_producer_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", tmp_path.as_posix())
    monkeypatch.setenv("KAFKA_PRODUCER_RETRIES", "11")
    monkeypatch.setenv("KAFKA_PRODUCER_RETRY_BACKOFF_MS", "333")
    monkeypatch.setenv("KAFKA_PRODUCER_RETRY_BACKOFF_MAX_MS", "7777")
    monkeypatch.setenv("KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS", "123456")
    monkeypatch.setenv("PRODUCER_RETRIES", "5")

    settings = ProcessingSettings.from_env()

    assert settings.producer_retries == 11
    assert settings.producer_retry_backoff_ms == 333
    assert settings.producer_retry_backoff_max_ms == 7777
    assert settings.producer_delivery_timeout_ms == 123456


def test_processing_settings_from_env_falls_back_to_legacy_producer_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", tmp_path.as_posix())
    monkeypatch.delenv("KAFKA_PRODUCER_RETRIES", raising=False)
    monkeypatch.delenv("KAFKA_PRODUCER_RETRY_BACKOFF_MS", raising=False)
    monkeypatch.delenv("KAFKA_PRODUCER_RETRY_BACKOFF_MAX_MS", raising=False)
    monkeypatch.delenv("KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS", raising=False)
    monkeypatch.setenv("PRODUCER_RETRIES", "12")
    monkeypatch.setenv("PRODUCER_RETRY_BACKOFF_MS", "444")
    monkeypatch.setenv("PRODUCER_RETRY_BACKOFF_MAX_MS", "8888")
    monkeypatch.setenv("PRODUCER_DELIVERY_TIMEOUT_MS", "654321")

    settings = ProcessingSettings.from_env()

    assert settings.producer_retries == 12
    assert settings.producer_retry_backoff_ms == 444
    assert settings.producer_retry_backoff_max_ms == 8888
    assert settings.producer_delivery_timeout_ms == 654321


def test_processing_readiness_succeeds_when_topics_and_artifacts_root_are_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.modules.runtime._list_kafka_topics",
        lambda bootstrap_servers: {
            "audio.segment.ready",
            "audio.features",
            "system.metrics",
        },
    )

    check_runtime_dependencies(_processing_settings(tmp_path))


def test_processing_readiness_fails_when_required_topic_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.modules.runtime._list_kafka_topics",
        lambda bootstrap_servers: {
            "audio.segment.ready",
            "audio.features",
        },
    )

    with pytest.raises(ProcessingReadinessError, match="system.metrics"):
        check_runtime_dependencies(_processing_settings(tmp_path))


def test_processing_readiness_fails_when_artifacts_root_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_artifacts_root = tmp_path / "missing"
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.modules.runtime._list_kafka_topics",
        lambda bootstrap_servers: {
            "audio.segment.ready",
            "audio.features",
            "system.metrics",
        },
    )

    with pytest.raises(ProcessingReadinessError, match="ARTIFACTS_ROOT"):
        check_runtime_dependencies(_processing_settings(missing_artifacts_root))


def test_classify_processing_failure_marks_retryable_artifact_errors() -> None:
    retryable_file_missing = classify_processing_failure(FileNotFoundError("missing"))
    retryable_checksum = classify_processing_failure(
        ArtifactChecksumMismatch("checksum mismatch")
    )
    terminal_stage = classify_processing_failure(
        ProcessingStageError("feature_publish_failed", "publish failed")
    )

    assert retryable_file_missing.failure_class == "artifact_not_ready"
    assert retryable_file_missing.retryable is True
    assert retryable_checksum.failure_class == "checksum_mismatch"
    assert retryable_checksum.retryable is True
    assert terminal_stage.failure_class == "feature_publish_failed"
    assert terminal_stage.retryable is False


def test_process_with_retry_retries_missing_artifact_until_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    attempts = {"count": 0}
    sleeps: list[float] = []

    def fake_process_event(
        self: ProcessingPipeline,
        producer: object,
        envelope: dict[str, object],
    ) -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise FileNotFoundError("artifact missing")
        return "ok"

    monkeypatch.setattr(ProcessingPipeline, "process_event", fake_process_event)
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.sleep",
        lambda delay_s: sleeps.append(delay_s),
    )

    result = pipeline._process_with_retry(
        RecordingProducer(),
        {
            "run_id": "demo-run",
            "trace_id": "run/demo-run/track/2",
            "payload": {
                "run_id": "demo-run",
                "track_id": 2,
                "segment_idx": 0,
            },
        },
        logger=_service_logger(),
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [0.25, 0.5]


def test_process_with_retry_does_not_retry_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    attempts = {"count": 0}
    sleeps: list[float] = []

    def fake_process_event(
        self: ProcessingPipeline,
        producer: object,
        envelope: dict[str, object],
    ) -> str:
        attempts["count"] += 1
        raise ProcessingStageError(
            "processing_failed",
            "dsp exploded",
        )

    monkeypatch.setattr(ProcessingPipeline, "process_event", fake_process_event)
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.sleep",
        lambda delay_s: sleeps.append(delay_s),
    )

    with pytest.raises(ProcessingStageError, match="dsp exploded"):
        pipeline._process_with_retry(
            RecordingProducer(),
            {
                "run_id": "demo-run",
                "trace_id": "run/demo-run/track/2",
                "payload": {
                    "run_id": "demo-run",
                    "track_id": 2,
                    "segment_idx": 0,
                },
            },
            logger=_service_logger(),
        )

    assert attempts["count"] == 1
    assert sleeps == []


def test_processing_run_commits_after_successful_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    message = FakeMessage(
        topic="audio.segment.ready",
        partition=0,
        offset=12,
        value=_build_segment_ready_bytes(tmp_path),
    )
    consumer = FakeConsumer([message, KeyboardInterrupt()])
    producer = RecordingProducer()

    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.check_runtime_dependencies",
        lambda settings: None,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_consumer",
        lambda **kwargs: consumer,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_producer",
        lambda **kwargs: producer,
    )

    with pytest.raises(KeyboardInterrupt):
        pipeline.run(logger=_service_logger())

    assert [commit.offset() for commit in consumer.commit_calls] == [12]
    assert consumer.close_calls == 1
    assert len(producer.messages) == 3


def test_processing_run_does_not_emit_feature_errors_when_offset_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    message = FakeMessage(
        topic="audio.segment.ready",
        partition=0,
        offset=27,
        value=_build_segment_ready_bytes(tmp_path),
    )
    consumer = CommitFailingConsumer([message])
    producer = RecordingProducer()

    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.check_runtime_dependencies",
        lambda settings: None,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_consumer",
        lambda **kwargs: consumer,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_producer",
        lambda **kwargs: producer,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        pipeline.run(logger=_service_logger())

    assert consumer.commit_calls == []
    assert consumer.poll_calls == 1
    assert consumer.close_calls == 1
    assert len(producer.messages) == 3
    assert not any(
        message["topic"] == "system.metrics"
        and message["value"]["payload"]["metric_name"] == "feature_errors"
        for message in producer.messages
    )


def test_processing_run_emits_feature_errors_and_keeps_offset_uncommitted_on_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    message = FakeMessage(
        topic="audio.segment.ready",
        partition=0,
        offset=99,
        value=_build_segment_ready_bytes(tmp_path),
    )
    consumer = FakeConsumer([message, KeyboardInterrupt()])
    producer = RecordingProducer()

    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.check_runtime_dependencies",
        lambda settings: None,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_consumer",
        lambda **kwargs: consumer,
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.processing.pipeline.build_producer",
        lambda **kwargs: producer,
    )
    def fake_process_with_retry(
        self: ProcessingPipeline,
        producer: object,
        envelope: dict[str, object],
        logger: ServiceLoggerAdapter,
    ) -> ProcessingStageError:
        raise FileNotFoundError("artifact missing")

    monkeypatch.setattr(
        ProcessingPipeline,
        "_process_with_retry",
        fake_process_with_retry,
    )

    with pytest.raises(FileNotFoundError, match="artifact missing"):
        pipeline.run(logger=_service_logger())

    assert consumer.commit_calls == []
    assert consumer.poll_calls == 1
    assert consumer.close_calls == 1

    error_metrics = [
        message
        for message in producer.messages
        if message["topic"] == "system.metrics"
        and message["value"]["payload"]["metric_name"] == "feature_errors"
    ]
    assert len(error_metrics) == 1
    assert error_metrics[0]["value"]["payload"]["labels_json"]["failure_class"] == "artifact_not_ready"


def test_json_formatter_includes_processing_runtime_context_fields() -> None:
    logger = logging.getLogger("processing-json-formatter-test")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    adapter = ServiceLoggerAdapter(
        logger,
        {
            "service_name": "processing",
            "run_id": "demo-run",
        },
    ).bind(
        trace_id="run/demo-run/track/2",
        track_id=2,
        segment_idx=0,
        topic="audio.segment.ready",
        partition=0,
        offset=12,
        attempt=2,
        metric_name="processing_ms",
        metric_value=12.5,
        silent_flag=False,
    )
    adapter.info("Structured processing log")

    payload = json.loads(stream.getvalue())
    assert payload["run_id"] == "demo-run"
    assert payload["trace_id"] == "run/demo-run/track/2"
    assert payload["track_id"] == 2
    assert payload["segment_idx"] == 0
    assert payload["topic"] == "audio.segment.ready"
    assert payload["partition"] == 0
    assert payload["offset"] == 12
    assert payload["attempt"] == 2
    assert payload["metric_name"] == "processing_ms"
    assert payload["metric_value"] == 12.5
    assert payload["silent_flag"] is False
