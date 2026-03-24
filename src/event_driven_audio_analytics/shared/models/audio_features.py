"""Payload model for the audio.features topic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AudioFeaturesPayload:
    """Feature summary emitted by the processing service."""

    ts: str
    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    rms: float
    silent_flag: bool
    mel_bins: int
    mel_frames: int
    processing_ms: float
