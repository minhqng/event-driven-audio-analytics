"""Claim-check artifact writing for ingestion-produced audio segments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import wave

import numpy as np
import polars as pl

from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.storage import manifest_uri, segment_artifact_uri

from .segmenter import AudioSegment


@dataclass(slots=True)
class SegmentDescriptor:
    """Claim-check descriptor for one persisted audio segment artifact."""

    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    sample_rate: int
    duration_s: float
    is_last_segment: bool


def ensure_artifact_layout(artifacts_root: Path, run_id: str) -> tuple[Path, Path]:
    """Return segment and manifest directories for a run."""

    segments_dir = artifacts_root / "runs" / run_id / "segments"
    manifests_dir = artifacts_root / "runs" / run_id / "manifests"
    segments_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    return segments_dir, manifests_dir


def _write_wav_mono(path: Path, waveform: np.ndarray, sample_rate: int) -> None:
    """Persist a mono float waveform as a 16-bit PCM WAV artifact."""

    clipped = np.clip(waveform[0], -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _manifest_frame(entries: list[SegmentDescriptor]) -> pl.DataFrame:
    """Convert written segment descriptors into a Parquet-friendly frame."""

    return pl.DataFrame([asdict(entry) for entry in entries])


def write_segment_artifacts(
    artifacts_root: Path,
    segments: list[AudioSegment],
) -> list[SegmentDescriptor]:
    """Write WAV artifacts, compute checksums, and update the run manifest."""

    if not segments:
        return []

    run_id = segments[0].run_id
    manifest_uri_str = manifest_uri(artifacts_root, run_id)
    manifest_path = Path(manifest_uri_str)
    ensure_artifact_layout(artifacts_root, run_id)

    descriptors: list[SegmentDescriptor] = []
    for segment in segments:
        artifact_uri_str = segment_artifact_uri(
            artifacts_root,
            segment.run_id,
            segment.track_id,
            segment.segment_idx,
        )
        artifact_path = Path(artifact_uri_str)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _write_wav_mono(artifact_path, segment.waveform, segment.sample_rate)
        descriptors.append(
            SegmentDescriptor(
                run_id=segment.run_id,
                track_id=segment.track_id,
                segment_idx=segment.segment_idx,
                artifact_uri=artifact_uri_str,
                checksum=sha256_file(artifact_path),
                manifest_uri=manifest_uri_str,
                sample_rate=segment.sample_rate,
                duration_s=segment.duration_s,
                is_last_segment=segment.is_last_segment,
            )
        )

    current_frame = _manifest_frame(descriptors)
    if manifest_path.exists():
        existing_frame = pl.read_parquet(manifest_path)
        current_frame = (
            pl.concat([existing_frame, current_frame], how="vertical_relaxed")
            .unique(subset=["run_id", "track_id", "segment_idx"], keep="last")
            .sort(["run_id", "track_id", "segment_idx"])
        )

    current_frame.write_parquet(manifest_path)
    return descriptors
