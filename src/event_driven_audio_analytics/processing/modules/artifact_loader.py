"""Claim-check artifact loading for processing."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import wave

import numpy as np

from event_driven_audio_analytics.shared.checksum import sha256_bytes
from event_driven_audio_analytics.shared.storage import (
    ClaimCheckStore,
    build_claim_check_store,
    storage_settings_for_local,
)


class ArtifactLoadError(RuntimeError):
    """Raised when a claim-check artifact cannot be loaded safely."""


class ArtifactChecksumMismatch(ArtifactLoadError):
    """Raised when an artifact checksum does not match the event payload."""


@dataclass(slots=True)
class LoadedSegmentArtifact:
    """Decoded claim-check artifact ready for DSP work."""

    artifact_uri: str
    artifact_path: Path | None
    checksum: str
    waveform: np.ndarray
    sample_rate_hz: int
    duration_s: float


def _decode_pcm_frames(*, frames: bytes, sample_width: int) -> np.ndarray:
    """Decode mono PCM frames into a normalized float waveform."""

    if sample_width == 1:
        waveform = np.frombuffer(frames, dtype=np.uint8).astype(np.float32, copy=False)
        waveform = (waveform - 128.0) / 128.0
    elif sample_width == 2:
        waveform = np.frombuffer(frames, dtype="<i2").astype(np.float32, copy=False)
        waveform = waveform / 32767.0
    elif sample_width == 4:
        waveform = np.frombuffer(frames, dtype="<i4").astype(np.float32, copy=False)
        waveform = waveform / 2147483647.0
    else:
        raise ArtifactLoadError(f"Unsupported PCM sample width: {sample_width} bytes.")

    return waveform[np.newaxis, :]


def load_segment_artifact(
    artifact_uri: str,
    checksum: str,
    *,
    artifacts_root: Path,
    expected_sample_rate_hz: int | None = None,
    store: ClaimCheckStore | None = None,
) -> LoadedSegmentArtifact:
    """Load a mono WAV segment artifact and verify its checksum first."""

    if store is None:
        store = build_claim_check_store(storage_settings_for_local(artifacts_root))

    payload = store.read_bytes(artifact_uri)
    actual_checksum = sha256_bytes(payload)
    if actual_checksum != checksum:
        raise ArtifactChecksumMismatch(
            "Segment artifact checksum mismatch "
            f"expected={checksum} actual={actual_checksum} "
            f"uri={artifact_uri}"
        )

    with wave.open(BytesIO(payload), "rb") as handle:
        if handle.getnchannels() != 1:
            raise ArtifactLoadError(
                "Segment artifact must be mono after ingestion normalization."
            )
        if handle.getcomptype() != "NONE":
            raise ArtifactLoadError(
                "Segment artifact must use uncompressed PCM WAV framing."
            )

        sample_rate_hz = int(handle.getframerate())
        if expected_sample_rate_hz is not None and sample_rate_hz != expected_sample_rate_hz:
            raise ArtifactLoadError(
                "Segment artifact sample rate does not match the claim-check event "
                f"expected={expected_sample_rate_hz} actual={sample_rate_hz}"
            )

        frame_count = int(handle.getnframes())
        waveform = _decode_pcm_frames(
            frames=handle.readframes(frame_count),
            sample_width=handle.getsampwidth(),
        )

    duration_s = frame_count / float(sample_rate_hz)
    return LoadedSegmentArtifact(
        artifact_uri=artifact_uri,
        artifact_path=store.local_path(artifact_uri),
        checksum=actual_checksum,
        waveform=waveform,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
    )
