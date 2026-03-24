"""Segmentation placeholders for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SegmentDescriptor:
    """Represents a segment that will be written to shared storage."""

    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    sample_rate: int
    duration_s: float
    is_last_segment: bool


def build_segment_plan(run_id: str, track_id: int) -> list[SegmentDescriptor]:
    """Return an empty segmentation plan until DSP logic is implemented."""

    # TODO: implement 3.0-second windows with 1.5-second overlap at 32 kHz mono.
    _ = (run_id, track_id)
    return []
