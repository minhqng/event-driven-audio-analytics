from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile

import numpy as np
import pytest
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_REFERENCE_ROOT = (
    REPO_ROOT / "references" / "legacy-fma-pipeline" / "fma-small-audio-pipeline-main"
)

if not LEGACY_REFERENCE_ROOT.exists():
    pytestmark = pytest.mark.skip(reason="legacy reference checkout is not available in this workspace")
else:
    sys.path.insert(0, str(LEGACY_REFERENCE_ROOT))
    try:
        from src.features.audio_transforms import AudioTransform as LegacyAudioTransform
    except ModuleNotFoundError as exc:
        pytestmark = pytest.mark.skip(
            reason=(
                "legacy reference dependencies are not available in this workspace "
                f"(missing {exc.name})."
            )
        )

from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_VALIDATED,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.artifact_writer import write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from event_driven_audio_analytics.processing.config import ProcessingSettings
from event_driven_audio_analytics.processing.pipeline import ProcessingPipeline
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.settings import BaseServiceSettings


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "audio"
SQL_PATH = REPO_ROOT / "infra" / "sql" / "002_core_tables.sql"
SCHEMA_PATH = REPO_ROOT / "schemas" / "events" / "audio.features.v1.json"


class RecordingProducer:
    def produce(
        self,
        *,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        on_delivery: object | None = None,
    ) -> None:
        if on_delivery is not None:
            on_delivery(None, None)

    def flush(self, timeout: float | None = None) -> int:
        return 0

    def poll(self, timeout: float = 0.0) -> int:
        return 0


def _legacy_transform() -> LegacyAudioTransform:
    return LegacyAudioTransform(
        sample_rate=32000,
        duration=3.0,
        segment_overlap=1.5,
        n_mels=128,
        n_fft=1024,
        hop_length=320,
        f_min=0,
        f_max=16000,
        norm_type="slaney",
        target_frames=300,
        log_epsilon=1e-9,
        device=torch.device("cpu"),
    )


def _processing_settings(artifacts_root: Path) -> ProcessingSettings:
    return ProcessingSettings(
        base=BaseServiceSettings(
            service_name="processing",
            run_id="reference-parity",
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


def _audio_features_table_columns() -> set[str]:
    sql = SQL_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS audio_features \((?P<body>.*?)\);",
        sql,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("audio_features table definition was not found in 002_core_tables.sql")

    columns: set[str] = set()
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("--") or line.startswith("PRIMARY KEY"):
            continue
        columns.add(line.split()[0])
    return columns


def test_decode_audio_pyav_matches_legacy_downmix_resample_semantics() -> None:
    fixture_path = FIXTURES_DIR / "valid_synthetic_stereo_44k1.mp3"
    record = MetadataRecord(
        track_id=2,
        artist_id=1,
        genre_label="Hip-Hop",
        subset="small",
        source_path="valid_synthetic_stereo_44k1.mp3",
        source_audio_uri=fixture_path.as_posix(),
        declared_duration_s=4.6,
    )
    validation = validate_audio_record(record, target_sample_rate_hz=32000)
    legacy_waveform = _legacy_transform().load_and_resample(fixture_path.as_posix()).numpy()

    assert validation.validation_status == VALIDATION_STATUS_VALIDATED
    assert validation.decoded_audio is not None
    assert validation.decoded_audio.waveform.shape == legacy_waveform.shape
    assert np.allclose(validation.decoded_audio.waveform, legacy_waveform, atol=1e-3)


def test_audio_features_mapping_stays_summary_first_without_feature_uri() -> None:
    payload_fields = set(AudioFeaturesPayload.__dataclass_fields__)
    schema_fields = set(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["payload"]["properties"]
    )
    sql_columns = _audio_features_table_columns() - {"created_at"}

    expected_fields = {
        "ts",
        "run_id",
        "track_id",
        "segment_idx",
        "artifact_uri",
        "checksum",
        "manifest_uri",
        "rms",
        "silent_flag",
        "mel_bins",
        "mel_frames",
        "processing_ms",
    }

    assert payload_fields == expected_fields
    assert schema_fields == expected_fields
    assert expected_fields <= sql_columns
    assert "feature_uri" not in payload_fields
    assert "feature_uri" not in schema_fields


def test_processing_summary_keeps_reference_shape_and_silence_semantics() -> None:
    fixture_path = FIXTURES_DIR / "valid_synthetic_stereo_44k1.mp3"
    record = MetadataRecord(
        track_id=2,
        artist_id=1,
        genre_label="Hip-Hop",
        subset="small",
        source_path="valid_synthetic_stereo_44k1.mp3",
        source_audio_uri=fixture_path.as_posix(),
        declared_duration_s=4.6,
    )
    validation = validate_audio_record(record, target_sample_rate_hz=32000)
    assert validation.validation_status == VALIDATION_STATUS_VALIDATED
    assert validation.decoded_audio is not None

    current_segments = segment_audio(
        run_id="reference-parity",
        track_id=record.track_id,
        waveform=validation.decoded_audio.waveform,
        sample_rate_hz=validation.decoded_audio.sample_rate_hz,
    )
    legacy_segments = _legacy_transform().extract_segments(
        _legacy_transform().load_and_resample(fixture_path.as_posix())
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        artifacts_root = Path(temp_dir)
        descriptors = write_segment_artifacts(artifacts_root, current_segments)
        pipeline = ProcessingPipeline(settings=_processing_settings(artifacts_root))
        producer = RecordingProducer()
        segment_mel_maes: list[float] = []

        for descriptor, legacy_segment in zip(descriptors, legacy_segments, strict=True):
            result = pipeline.process_payload(
                producer,
                AudioSegmentReadyPayload(
                    run_id=descriptor.run_id,
                    track_id=descriptor.track_id,
                    segment_idx=descriptor.segment_idx,
                    artifact_uri=descriptor.artifact_uri,
                    checksum=descriptor.checksum,
                    sample_rate=descriptor.sample_rate,
                    duration_s=descriptor.duration_s,
                    is_last_segment=descriptor.is_last_segment,
                    manifest_uri=descriptor.manifest_uri,
                ),
            )
            legacy_mel = _legacy_transform().to_mel_spectrogram(legacy_segment)
            segment_mel_maes.append(float(torch.mean(torch.abs(result.mel - legacy_mel)).item()))

            assert tuple(int(dimension) for dimension in result.mel.shape) == (1, 128, 300)
            assert result.silent_flag is False
            assert result.rms_summary.rms_dbfs == pytest.approx(
                20.0 * np.log10(np.sqrt(np.mean(np.square(legacy_segment.numpy()), dtype=np.float64))),
                abs=0.01,
            )

    assert len(current_segments) == len(legacy_segments) == 3
    assert max(segment_mel_maes) <= 0.5
