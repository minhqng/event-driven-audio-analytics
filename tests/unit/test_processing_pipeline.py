from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import wave

import numpy as np
import pytest

from event_driven_audio_analytics.ingestion.modules.artifact_writer import write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_VALIDATED,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord
from event_driven_audio_analytics.ingestion.modules.publisher import build_segment_ready_event
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from event_driven_audio_analytics.processing.config import ProcessingSettings
from event_driven_audio_analytics.processing.modules.artifact_loader import (
    ArtifactChecksumMismatch,
    load_segment_artifact,
)
from event_driven_audio_analytics.processing.modules.metrics import processing_metrics_state_path
from event_driven_audio_analytics.processing.modules.rms import summarize_rms
from event_driven_audio_analytics.processing.modules.welford import build_welford_state_ref
from event_driven_audio_analytics.processing.pipeline import (
    ProcessingPipeline,
    ProcessingStageError,
)
from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.kafka import deserialize_envelope
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import validate_envelope_dict
from event_driven_audio_analytics.shared.settings import BaseServiceSettings
from tests.unit.test_event_contract_validation import load_validator


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
AUDIO_FEATURES_V1_VALIDATOR = load_validator("audio.features.v1.json")


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
            on_delivery(None, _DeliveredMessage(topic))

    def flush(self, timeout: float | None = None) -> int:
        return 0

    def poll(self, timeout: float = 0.0) -> int:
        return 0


class FailingProducer(RecordingProducer):
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
            on_delivery(RuntimeError("broker unavailable"), None)


class FailAfterNProducer(RecordingProducer):
    def __init__(self, fail_on_produce_call: int) -> None:
        super().__init__()
        self._produce_calls = 0
        self._fail_on_produce_call = fail_on_produce_call

    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: object | None = None,
    ) -> None:
        self._produce_calls += 1
        self.messages.append(
            {
                "topic": topic,
                "key": key.decode("utf-8") if key is not None else None,
                "value": deserialize_envelope(value),
            }
        )
        if on_delivery is not None:
            if self._produce_calls == self._fail_on_produce_call:
                on_delivery(RuntimeError("broker unavailable"), None)
            else:
                on_delivery(None, _DeliveredMessage(topic))


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
        artifact_retry_attempts=5,
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
    duration_s: float,
    sample_rate_hz: int = 32000,
    amplitude: float = 0.2,
    frequency_hz: float = 440.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = int(round(duration_s * sample_rate_hz))
    timeline = np.arange(sample_count, dtype=np.float64) / float(sample_rate_hz)
    waveform = amplitude * np.sin(2.0 * np.pi * frequency_hz * timeline)
    pcm = np.round(np.clip(waveform, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(pcm.tobytes())


def _copy_fixture_under_artifacts_root(
    artifacts_root: Path,
    fixture_name: str,
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
) -> Path:
    artifact_path = (
        artifacts_root
        / "runs"
        / run_id
        / "segments"
        / str(track_id)
        / f"{segment_idx}.wav"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES_DIR / fixture_name, artifact_path)
    return artifact_path


def _segment_ready_payload_for_artifact(
    artifact_path: Path,
    *,
    run_id: str = "demo-run",
    track_id: int,
    segment_idx: int,
    duration_s: float,
    manifest_uri: str | None = None,
) -> AudioSegmentReadyPayload:
    return AudioSegmentReadyPayload(
        run_id=run_id,
        track_id=track_id,
        segment_idx=segment_idx,
        artifact_uri=artifact_path.as_posix(),
        checksum=sha256_file(artifact_path),
        sample_rate=32000,
        duration_s=duration_s,
        is_last_segment=True,
        manifest_uri=manifest_uri,
    )


def _build_ingestion_owned_segment_descriptor(tmp_path: Path):
    record = MetadataRecord(
        track_id=2,
        artist_id=1,
        genre_label="Hip-Hop",
        subset="small",
        source_path="valid_synthetic_stereo_44k1.mp3",
        source_audio_uri=(FIXTURES_DIR / "valid_synthetic_stereo_44k1.mp3").as_posix(),
        declared_duration_s=4.6,
    )
    validation = validate_audio_record(record, target_sample_rate_hz=32000)
    assert validation.validation_status == VALIDATION_STATUS_VALIDATED
    assert validation.decoded_audio is not None

    segments = segment_audio(
        run_id="demo-run",
        track_id=record.track_id,
        waveform=validation.decoded_audio.waveform,
        sample_rate_hz=validation.decoded_audio.sample_rate_hz,
    )
    descriptors = write_segment_artifacts(tmp_path, [segments[0]])
    return descriptors[0]


def _assert_valid_audio_features_envelope(envelope: dict[str, object]) -> None:
    AUDIO_FEATURES_V1_VALIDATOR.validate(envelope)
    validate_envelope_dict(envelope, expected_event_type="audio.features")


def test_segment_loader_reads_claim_check_artifact_and_validates_checksum(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path, duration_s=3.0)

    artifact = load_segment_artifact(
        artifact_path.as_posix(),
        sha256_file(artifact_path),
        artifacts_root=tmp_path,
        expected_sample_rate_hz=32000,
    )

    assert artifact.artifact_path == artifact_path
    assert artifact.sample_rate_hz == 32000
    assert artifact.duration_s == pytest.approx(3.0, abs=1e-6)
    assert artifact.waveform.shape == (1, 96000)


def test_segment_loader_rejects_checksum_mismatch(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path, duration_s=3.0)

    with pytest.raises(ArtifactChecksumMismatch, match="checksum mismatch"):
        load_segment_artifact(
            artifact_path.as_posix(),
            "sha256:not-the-real-digest",
            artifacts_root=tmp_path,
            expected_sample_rate_hz=32000,
        )


def test_segment_loader_rejects_artifact_uri_outside_artifacts_root(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    outside_artifact = tmp_path / "outside.wav"
    _write_tone_wav(outside_artifact, duration_s=3.0)

    with pytest.raises(ValueError, match="artifacts_root"):
        load_segment_artifact(
            outside_artifact.as_posix(),
            sha256_file(outside_artifact),
            artifacts_root=artifacts_root,
            expected_sample_rate_hz=32000,
        )


def test_rms_summary_matches_expected_dbfs_for_tone_fixture(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path, duration_s=3.0, amplitude=0.2)

    artifact = load_segment_artifact(
        artifact_path.as_posix(),
        sha256_file(artifact_path),
        artifacts_root=tmp_path,
        expected_sample_rate_hz=32000,
    )
    summary = summarize_rms(artifact.waveform)
    expected_dbfs = 20.0 * math.log10(0.2 / math.sqrt(2.0))

    assert summary.rms_linear == pytest.approx(0.2 / math.sqrt(2.0), abs=2e-4)
    assert summary.rms_dbfs == pytest.approx(expected_dbfs, abs=0.05)


def test_processing_pipeline_emits_audio_features_from_claim_check_artifact(tmp_path: Path) -> None:
    descriptor = _build_ingestion_owned_segment_descriptor(tmp_path)
    payload = AudioSegmentReadyPayload(
        run_id=descriptor.run_id,
        track_id=descriptor.track_id,
        segment_idx=descriptor.segment_idx,
        artifact_uri=descriptor.artifact_uri,
        checksum=descriptor.checksum,
        sample_rate=descriptor.sample_rate,
        duration_s=descriptor.duration_s,
        is_last_segment=descriptor.is_last_segment,
        manifest_uri=descriptor.manifest_uri,
    )
    envelope = build_segment_ready_event(payload).to_dict()
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    result = pipeline.process_event(producer, envelope)

    assert tuple(int(dimension) for dimension in result.mel.shape) == (1, 128, 300)
    assert result.silent_flag is False
    assert result.silent_ratio == pytest.approx(0.0)
    assert result.welford_state_ref == build_welford_state_ref("demo-run")
    assert pipeline.run_metrics.successful_segments == 1
    assert pipeline.run_metrics.silent_segments == 0
    assert len(producer.messages) == 3

    feature_messages = [message for message in producer.messages if message["topic"] == "audio.features"]
    metric_messages = [message for message in producer.messages if message["topic"] == "system.metrics"]
    assert len(feature_messages) == 1
    assert len(metric_messages) == 2

    produced_message = feature_messages[0]
    assert produced_message["topic"] == "audio.features"
    assert produced_message["key"] == str(payload.track_id)

    produced_envelope = produced_message["value"]
    assert isinstance(produced_envelope, dict)
    _assert_valid_audio_features_envelope(produced_envelope)
    assert produced_envelope["trace_id"] == envelope["trace_id"]
    produced_payload = produced_envelope["payload"]
    assert produced_payload["run_id"] == payload.run_id
    assert produced_payload["track_id"] == payload.track_id
    assert produced_payload["segment_idx"] == payload.segment_idx
    assert produced_payload["artifact_uri"] == payload.artifact_uri
    assert produced_payload["checksum"] == payload.checksum
    assert produced_payload["mel_bins"] == 128
    assert produced_payload["mel_frames"] == 300
    assert produced_payload["silent_flag"] is False
    assert produced_payload["processing_ms"] >= 0.0
    assert produced_payload["manifest_uri"] == payload.manifest_uri

    metric_payloads = [message["value"]["payload"] for message in metric_messages]
    processing_ms_payload = next(
        metric_payload for metric_payload in metric_payloads if metric_payload["metric_name"] == "processing_ms"
    )
    silent_ratio_payload = next(
        metric_payload for metric_payload in metric_payloads if metric_payload["metric_name"] == "silent_ratio"
    )
    assert processing_ms_payload["service_name"] == "processing"
    assert processing_ms_payload["labels_json"] == {"topic": "audio.features", "status": "ok"}
    assert processing_ms_payload["unit"] == "ms"
    assert processing_ms_payload["metric_value"] == pytest.approx(produced_payload["processing_ms"])
    assert silent_ratio_payload["service_name"] == "processing"
    assert silent_ratio_payload["labels_json"] == {"scope": "run_total"}
    assert silent_ratio_payload["unit"] == "ratio"
    assert silent_ratio_payload["metric_value"] == pytest.approx(0.0)


def test_processing_pipeline_marks_silent_fixture_and_clamps_transport_rms(tmp_path: Path) -> None:
    artifact_path = _copy_fixture_under_artifacts_root(
        tmp_path,
        "silent_mono_32k.wav",
        run_id="demo-run",
        track_id=77,
        segment_idx=0,
    )
    payload = _segment_ready_payload_for_artifact(
        artifact_path,
        track_id=77,
        segment_idx=0,
        duration_s=3.0,
    )
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    result = pipeline.process_payload(producer, payload)

    assert result.silent_flag is True
    assert result.silent_ratio == pytest.approx(1.0)
    assert not math.isfinite(result.rms_summary.rms_dbfs)
    assert result.welford_state.count == 1
    assert pipeline.run_metrics.successful_segments == 1
    assert pipeline.run_metrics.silent_segments == 1
    produced_envelope = next(
        message["value"] for message in producer.messages if message["topic"] == "audio.features"
    )
    assert isinstance(produced_envelope, dict)
    _assert_valid_audio_features_envelope(produced_envelope)
    assert produced_envelope["payload"]["silent_flag"] is True
    assert produced_envelope["payload"]["rms"] == pytest.approx(-60.0)


def test_silent_ratio_stays_scoped_to_each_run_id(tmp_path: Path) -> None:
    silent_artifact = _copy_fixture_under_artifacts_root(
        tmp_path,
        "silent_mono_32k.wav",
        run_id="demo-run",
        track_id=77,
        segment_idx=0,
    )
    tone_artifact = tmp_path / "tone.wav"
    _write_tone_wav(tone_artifact, duration_s=3.0)
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    first_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            silent_artifact,
            run_id="demo-run",
            track_id=77,
            segment_idx=0,
            duration_s=3.0,
        ),
    )
    second_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            tone_artifact,
            run_id="other-run",
            track_id=88,
            segment_idx=0,
            duration_s=3.0,
        ),
    )

    assert first_result.silent_ratio == pytest.approx(1.0)
    assert second_result.silent_ratio == pytest.approx(0.0)
    assert pipeline.run_metrics_for("demo-run").successful_segments == 1
    assert pipeline.run_metrics_for("demo-run").silent_segments == 1
    assert pipeline.run_metrics_for("other-run").successful_segments == 1
    assert pipeline.run_metrics_for("other-run").silent_segments == 0

    other_run_silent_ratio_payload = next(
        message["value"]["payload"]
        for message in producer.messages
        if message["topic"] == "system.metrics"
        and message["value"]["run_id"] == "other-run"
        and message["value"]["payload"]["metric_name"] == "silent_ratio"
    )
    assert other_run_silent_ratio_payload["metric_value"] == pytest.approx(0.0)


def test_silent_ratio_recovers_from_persisted_run_state_after_restart(tmp_path: Path) -> None:
    silent_artifact = _copy_fixture_under_artifacts_root(
        tmp_path,
        "silent_mono_32k.wav",
        run_id="demo-run",
        track_id=77,
        segment_idx=0,
    )
    tone_artifact = tmp_path / "tone.wav"
    _write_tone_wav(tone_artifact, duration_s=3.0)
    first_pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    replay_pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    first_result = first_pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            silent_artifact,
            run_id="demo-run",
            track_id=77,
            segment_idx=0,
            duration_s=3.0,
        ),
    )
    second_result = replay_pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            tone_artifact,
            run_id="demo-run",
            track_id=78,
            segment_idx=1,
            duration_s=3.0,
        ),
    )

    state_payload = json.loads(
        processing_metrics_state_path(tmp_path, "demo-run").read_text(encoding="utf-8")
    )
    assert first_result.silent_ratio == pytest.approx(1.0)
    assert second_result.silent_ratio == pytest.approx(0.5)
    assert replay_pipeline.run_metrics.successful_segments == 2
    assert replay_pipeline.run_metrics.silent_segments == 1
    assert len(state_payload["segments"]) == 2


def test_replayed_segment_keeps_silent_ratio_stable_after_restart(tmp_path: Path) -> None:
    silent_artifact = _copy_fixture_under_artifacts_root(
        tmp_path,
        "silent_mono_32k.wav",
        run_id="demo-run",
        track_id=77,
        segment_idx=0,
    )
    first_pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    replay_pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    first_result = first_pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            silent_artifact,
            run_id="demo-run",
            track_id=77,
            segment_idx=0,
            duration_s=3.0,
        ),
    )
    replay_result = replay_pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            silent_artifact,
            run_id="demo-run",
            track_id=77,
            segment_idx=0,
            duration_s=3.0,
        ),
    )

    state_payload = json.loads(
        processing_metrics_state_path(tmp_path, "demo-run").read_text(encoding="utf-8")
    )
    assert first_result.silent_ratio == pytest.approx(1.0)
    assert replay_result.silent_ratio == pytest.approx(1.0)
    assert replay_pipeline.run_metrics.successful_segments == 1
    assert replay_pipeline.run_metrics.silent_segments == 1
    assert len(state_payload["segments"]) == 1


def test_welford_state_stays_scoped_to_each_run_id(tmp_path: Path) -> None:
    first_artifact = tmp_path / "first-tone.wav"
    second_artifact = tmp_path / "second-tone.wav"
    _write_tone_wav(first_artifact, duration_s=3.0, amplitude=0.2, frequency_hz=440.0)
    _write_tone_wav(second_artifact, duration_s=3.0, amplitude=0.1, frequency_hz=880.0)
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    first_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            first_artifact,
            run_id="demo-run",
            track_id=90,
            segment_idx=0,
            duration_s=3.0,
        ),
    )
    second_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            second_artifact,
            run_id="other-run",
            track_id=91,
            segment_idx=0,
            duration_s=3.0,
        ),
    )

    demo_run_state = pipeline.welford_state_for("demo-run")
    other_run_state = pipeline.welford_state_for("other-run")

    assert demo_run_state.count == 1
    assert other_run_state.count == 1
    assert demo_run_state.ref == build_welford_state_ref("demo-run")
    assert other_run_state.ref == build_welford_state_ref("other-run")
    assert first_result.welford_state_ref == build_welford_state_ref("demo-run")
    assert second_result.welford_state_ref == build_welford_state_ref("other-run")
    assert demo_run_state.mean is not None
    assert other_run_state.mean is not None
    assert not np.allclose(demo_run_state.mean, other_run_state.mean)


def test_short_clip_fixture_keeps_exact_mel_shape(tmp_path: Path) -> None:
    artifact_path = _copy_fixture_under_artifacts_root(
        tmp_path,
        "short_tone_mono_32k.wav",
        run_id="demo-run",
        track_id=88,
        segment_idx=0,
    )
    payload = _segment_ready_payload_for_artifact(
        artifact_path,
        track_id=88,
        segment_idx=0,
        duration_s=0.75,
    )
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    result = pipeline.process_payload(producer, payload)

    assert tuple(int(dimension) for dimension in result.mel.shape) == (1, 128, 300)
    produced_envelope = producer.messages[0]["value"]
    assert isinstance(produced_envelope, dict)
    _assert_valid_audio_features_envelope(produced_envelope)
    assert produced_envelope["payload"]["mel_bins"] == 128
    assert produced_envelope["payload"]["mel_frames"] == 300


def test_welford_updates_match_manual_per_bin_statistics(tmp_path: Path) -> None:
    tone_artifact = tmp_path / "tone.wav"
    _write_tone_wav(tone_artifact, duration_s=3.0, amplitude=0.15, frequency_hz=523.25)
    short_artifact = _copy_fixture_under_artifacts_root(
        tmp_path,
        "short_tone_mono_32k.wav",
        run_id="demo-run",
        track_id=101,
        segment_idx=0,
    )
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))
    producer = RecordingProducer()

    tone_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            tone_artifact,
            track_id=100,
            segment_idx=0,
            duration_s=3.0,
        ),
    )
    short_result = pipeline.process_payload(
        producer,
        _segment_ready_payload_for_artifact(
            short_artifact,
            track_id=101,
            segment_idx=0,
            duration_s=0.75,
        ),
    )

    expected_sample_means = np.vstack(
        [
            tone_result.mel.squeeze(0).mean(dim=1).numpy(),
            short_result.mel.squeeze(0).mean(dim=1).numpy(),
        ]
    ).astype(np.float64)
    expected_mean = expected_sample_means.mean(axis=0)
    expected_std = expected_sample_means.std(axis=0, ddof=1)

    state = pipeline.welford_state
    assert state.count == 2
    assert state.ref == build_welford_state_ref("demo-run")
    assert state.mean is not None
    assert state.std is not None
    assert np.allclose(state.mean, expected_mean)
    assert np.allclose(state.std, expected_std)
    assert pipeline.run_metrics.successful_segments == 2
    assert pipeline.run_metrics.silent_segments == 0


def test_processing_rejects_non_32khz_segment_ready_event(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone_44k1.wav"
    _write_tone_wav(artifact_path, duration_s=3.0, sample_rate_hz=44100)
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))

    with pytest.raises(ValueError, match="locked processing target"):
        pipeline.process_payload(
            RecordingProducer(),
            AudioSegmentReadyPayload(
                run_id="demo-run",
                track_id=102,
                segment_idx=0,
                artifact_uri=artifact_path.as_posix(),
                checksum=sha256_file(artifact_path),
                sample_rate=44100,
                duration_s=3.0,
                is_last_segment=True,
            ),
        )

    assert pipeline.welford_state.count == 0


def test_welford_state_does_not_advance_when_feature_publish_fails(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path, duration_s=3.0)
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))

    with pytest.raises(ProcessingStageError, match="audio.features"):
        pipeline.process_payload(
            FailingProducer(),
            _segment_ready_payload_for_artifact(
                artifact_path,
                track_id=103,
                segment_idx=0,
                duration_s=3.0,
            ),
        )

    assert pipeline.welford_state.count == 0
    assert pipeline.run_metrics.successful_segments == 0
    assert pipeline.run_metrics.silent_segments == 0


def test_run_metrics_do_not_advance_when_metric_publish_fails(tmp_path: Path) -> None:
    artifact_path = tmp_path / "tone.wav"
    _write_tone_wav(artifact_path, duration_s=3.0)
    pipeline = ProcessingPipeline(settings=_processing_settings(tmp_path))

    with pytest.raises(ProcessingStageError, match="system.metrics"):
        pipeline.process_payload(
            FailAfterNProducer(fail_on_produce_call=2),
            _segment_ready_payload_for_artifact(
                artifact_path,
                track_id=104,
                segment_idx=0,
                duration_s=3.0,
            ),
        )

    assert pipeline.welford_state.count == 0
    assert pipeline.run_metrics.successful_segments == 0
    assert pipeline.run_metrics.silent_segments == 0
