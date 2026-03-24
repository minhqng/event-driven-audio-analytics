"""Payload model for the audio.segment.ready topic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AudioSegmentReadyPayload:
    """Claim-check reference for a segment that is ready for processing."""

    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    sample_rate: int
    duration_s: float
    is_last_segment: bool
