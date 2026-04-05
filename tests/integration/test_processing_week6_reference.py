from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
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
    from src.features.audio_transforms import AudioTransform as LegacyAudioTransform

from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_VALIDATED,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.artifact_writer import write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.metadata_loader import load_small_subset_metadata
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from event_driven_audio_analytics.processing.config import ProcessingSettings
from event_driven_audio_analytics.processing.modules.welford import mel_bin_means
from event_driven_audio_analytics.processing.pipeline import ProcessingPipeline
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.settings import BaseServiceSettings


SINGLE_TRACK_IDS = (2,)
MULTI_TRACK_IDS = (2, 140, 148, 666, 1482)


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


@dataclass(slots=True)
class ReferenceParitySummary:
    track_ids: tuple[int, ...]
    segments_by_track: dict[int, int]
    total_segments: int
    max_rms_diff_db: float
    avg_rms_diff_db: float
    max_segment_mel_mae: float
    avg_segment_mel_mae: float
    silent_mismatch_count: int
    welford_mean_mae: float
    welford_std_mae: float


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


def _processing_settings(artifacts_root: Path, *, run_id: str) -> ProcessingSettings:
    return ProcessingSettings(
        base=BaseServiceSettings(
            service_name="processing",
            run_id=run_id,
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


def _reference_paths() -> tuple[Path, Path]:
    metadata_csv_path = (
        os.getenv("REFERENCE_METADATA_CSV_PATH")
        or os.getenv("WEEK6_REFERENCE_METADATA_CSV_PATH")
    )
    audio_root_path = (
        os.getenv("REFERENCE_AUDIO_ROOT_PATH")
        or os.getenv("WEEK6_REFERENCE_AUDIO_ROOT_PATH")
    )
    if not metadata_csv_path or not audio_root_path:
        pytest.skip(
            "Reference FMA inputs are not configured. Set REFERENCE_METADATA_CSV_PATH and "
            "REFERENCE_AUDIO_ROOT_PATH to run Week 6 parity integration tests."
        )

    metadata_csv = Path(metadata_csv_path)
    audio_root = Path(audio_root_path)
    if not metadata_csv.is_file() or not audio_root.is_dir():
        pytest.skip(
            "Reference FMA inputs are unavailable for Week 6 parity integration tests."
        )

    return (metadata_csv, audio_root)


def _run_reference_parity(track_ids: tuple[int, ...]) -> ReferenceParitySummary:
    metadata_csv, audio_root = _reference_paths()
    records = load_small_subset_metadata(
        str(metadata_csv),
        audio_root_path=str(audio_root),
        track_id_allowlist=track_ids,
    )
    if tuple(record.track_id for record in records) != track_ids:
        pytest.skip(
            "Reference FMA inputs do not contain the full Week 6 track set "
            f"expected={track_ids} loaded={[record.track_id for record in records]}."
        )

    legacy_transform = _legacy_transform()
    with tempfile.TemporaryDirectory() as temp_dir:
        artifacts_root = Path(temp_dir)
        pipeline = ProcessingPipeline(
            settings=_processing_settings(
                artifacts_root,
                run_id=f"week6-reference-{'-'.join(str(track_id) for track_id in track_ids)}",
            )
        )
        producer = RecordingProducer()
        segments_by_track: dict[int, int] = {}
        segment_mel_maes: list[float] = []
        rms_diffs: list[float] = []
        silent_mismatch_count = 0
        current_welford_samples: list[np.ndarray] = []
        legacy_welford_samples: list[np.ndarray] = []

        for record in records:
            validation = validate_audio_record(record, target_sample_rate_hz=32000)
            assert validation.validation_status == VALIDATION_STATUS_VALIDATED
            assert validation.decoded_audio is not None

            current_segments = segment_audio(
                run_id=pipeline.settings.base.run_id,
                track_id=record.track_id,
                waveform=validation.decoded_audio.waveform,
                sample_rate_hz=validation.decoded_audio.sample_rate_hz,
            )
            legacy_segments = legacy_transform.extract_segments(
                legacy_transform.load_and_resample(record.source_audio_uri)
            )
            segments_by_track[record.track_id] = len(current_segments)
            assert len(current_segments) == len(legacy_segments)

            descriptors = write_segment_artifacts(artifacts_root, current_segments)
            for descriptor, legacy_segment in zip(descriptors, legacy_segments, strict=True):
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
                result = pipeline.process_payload(
                    producer,
                    payload,
                    trace_id=f"run/{pipeline.settings.base.run_id}/track/{record.track_id}",
                )
                legacy_mel = legacy_transform.to_mel_spectrogram(legacy_segment)
                segment_mel_maes.append(float(torch.mean(torch.abs(result.mel - legacy_mel)).item()))

                legacy_rms_linear = float(
                    np.sqrt(np.mean(np.square(legacy_segment.numpy()), dtype=np.float64))
                )
                legacy_rms_db = (
                    -math.inf if legacy_rms_linear < 1e-10 else 20.0 * math.log10(legacy_rms_linear)
                )
                rms_diffs.append(abs(result.rms_summary.rms_dbfs - legacy_rms_db))

                legacy_silent_flag = bool(legacy_mel.std().item() < 1e-7)
                if result.silent_flag != legacy_silent_flag:
                    silent_mismatch_count += 1

                current_welford_samples.append(mel_bin_means(result.mel))
                legacy_welford_samples.append(mel_bin_means(legacy_mel))

        current_welford = np.vstack(current_welford_samples)
        legacy_welford = np.vstack(legacy_welford_samples)
        welford_mean_mae = float(
            np.abs(current_welford.mean(axis=0) - legacy_welford.mean(axis=0)).mean()
        )
        if len(current_welford) < 2:
            welford_std_mae = 0.0
        else:
            welford_std_mae = float(
                np.abs(
                    current_welford.std(axis=0, ddof=1) - legacy_welford.std(axis=0, ddof=1)
                ).mean()
            )

        return ReferenceParitySummary(
            track_ids=track_ids,
            segments_by_track=segments_by_track,
            total_segments=sum(segments_by_track.values()),
            max_rms_diff_db=max(rms_diffs),
            avg_rms_diff_db=sum(rms_diffs) / len(rms_diffs),
            max_segment_mel_mae=max(segment_mel_maes),
            avg_segment_mel_mae=sum(segment_mel_maes) / len(segment_mel_maes),
            silent_mismatch_count=silent_mismatch_count,
            welford_mean_mae=welford_mean_mae,
            welford_std_mae=welford_std_mae,
        )


def test_reference_parity_on_single_track() -> None:
    summary = _run_reference_parity(SINGLE_TRACK_IDS)

    assert summary.segments_by_track == {2: 19}
    assert summary.total_segments == 19
    assert summary.silent_mismatch_count == 0
    assert summary.max_rms_diff_db <= 0.01
    assert summary.max_segment_mel_mae <= 0.05
    assert summary.welford_mean_mae <= 0.02
    assert summary.welford_std_mae <= 0.001


def test_reference_parity_on_five_tracks() -> None:
    summary = _run_reference_parity(MULTI_TRACK_IDS)

    assert summary.segments_by_track == {
        2: 19,
        140: 19,
        148: 19,
        666: 20,
        1482: 19,
    }
    assert summary.total_segments == 96
    assert summary.silent_mismatch_count == 0
    assert summary.max_rms_diff_db <= 0.01
    assert summary.max_segment_mel_mae <= 0.05
    assert summary.welford_mean_mae <= 0.03
    assert summary.welford_std_mae <= 0.02
